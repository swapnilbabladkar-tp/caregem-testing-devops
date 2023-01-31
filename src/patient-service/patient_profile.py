import json
import logging
import os

import boto3
from custom_exception import GeneralException
from medical_info import MedicalType
from patient_utils import (
    get_chat_summary_base_query,
    get_notification_level_from_network,
)
from shared import (
    decrypt,
    find_user_by_external_id,
    find_user_by_internal_id,
    get_db_connect,
    get_headers,
    get_org_name,
    get_phi_data,
    get_phi_data_list,
    get_secret_manager,
    get_user_details_from_external_id,
    get_user_org_ids,
    read_as_dict,
    strip_dashes,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

cnx = get_db_connect()


key_object = get_secret_manager(os.getenv("ENCRYPTION_KEY_SECRET_ID"))


def get_connected_user_of_patient(cnx, patient_id, roles=None, specialty=None):
    """
    Connected Users of patient
    """
    n_roles = True if roles else None
    query = """ SELECT networks.user_internal_id AS user_internal_id,
                       networks.id               AS networks_id,
                       providers.id              AS id,
                       providers.external_id     AS external_id,
                       providers.internal_id     AS internal_id,
                       providers.`role`          AS `role`,
                       providers.`group`         AS `group`,
                       providers.degree          As degree,
                       providers.specialty       AS specialty
                FROM   networks
                       INNER JOIN patients
                               ON patients.id = networks._patient_id
                       JOIN providers
                               ON providers.internal_id = networks.user_internal_id
                WHERE  networks._patient_id = %(patient_id)s
                AND   (%(n_roles)s is NULL OR providers.`role` IN %(roles)s)
                AND   (%(specialty)s is NULL OR providers.specialty LIKE %(specialty)s)
            """
    params = {
        "patient_id": patient_id,
        "n_roles": n_roles,
        "roles": tuple(roles) if roles else tuple(" "),
        "specialty": "%" + specialty + "%" if specialty else None,
    }
    results = []
    prv_data = read_as_dict(cnx, query, params)
    if prv_data:
        results.extend(prv_data)
    if roles and "caregivers" not in roles:
        pass
    else:
        query = """ SELECT networks.user_internal_id AS user_internal_id,
                       networks.id               AS networks_id,
                       caregivers.id                 AS id,
                       caregivers.external_id        AS external_id,
                       caregivers.internal_id        AS internal_id,
                       'caregivers'                  AS `role`
                FROM   networks
                       INNER JOIN patients
                               ON patients.id = networks._patient_id
                       JOIN caregivers
                               ON caregivers.internal_id = networks.user_internal_id
                WHERE  networks._patient_id = %s
            """
        caregiver_data = read_as_dict(cnx, query, patient_id)
        if caregiver_data:
            results.extend(caregiver_data)
    return results


def get_appointment_by_internal_id(cnx, pat_int_id):
    """
    Get Appointment By Internal ID
    """
    query = """ SELECT appointments.id                   AS id,
                       appointments.patient_internal_id  AS patient_internal_id,
                       appointments.provider_internal_id AS provider_internal_id,
                       appointments.date_time            AS date_time,
                       appointments.active               AS active
                FROM   appointments
                WHERE  appointments.patient_internal_id = %s
                       AND appointments.active = 1
            """
    appointment_list = read_as_dict(cnx, query, (pat_int_id))
    appointment_dict = {
        str(appointment["provider_internal_id"]): (
            str(appointment["id"]),
            appointment["date_time"].strftime("%Y-%m-%d %H:%M"),
        )
        for appointment in appointment_list
    }
    return appointment_dict


def summary_user_chats(cnx, auth, add_patient_id):
    """
    Returns lastMessage, lastMessage timestamp and unread messages
    from the Old Chat history message data for the patient
    """
    username = auth["username"]
    query = get_chat_summary_base_query()
    chat_list = read_as_dict(cnx, query, (username, username))
    chat_list_summary_dict = {}
    for chat in chat_list:
        chat_summary = {}
        chat_summary["lastMessage"] = decrypt(chat["lastMessage"], key_object)
        chat_summary["timestamp"] = chat["timestamp"]
        if (
            chat["unreadMessages"]
            and chat["unreadMessages"] > 0
            and auth["internal_id"] != chat["sender_int_id"]
        ):
            chat_summary["unreadMessages"] = chat["unreadMessages"]
        else:
            chat_summary["unreadMessages"] = None
        if add_patient_id:
            summary_key = (str(chat["id"]), str(chat["internal_id"]))
        else:
            summary_key = str(chat["id"])
        chat_list_summary_dict.update({summary_key: chat_summary})
    return chat_list_summary_dict


def get_notification_level_from_network_by_id(cnx, auth_internal_id, pat_int_id):
    """
    Get Notification Level data for the selected patient
    """
    patient_notification = get_notification_level_from_network(
        cnx, auth_internal_id, pat_int_id
    )
    if len(patient_notification) > 1:
        notification_dict = patient_notification[0]
    else:
        med_list_obj_empty = []
        for i in range(len(MedicalType.ordered_list)):
            med_list_obj_empty.append(
                {"id": i, "desc": MedicalType.ordered_list[i], "level": 0}
            )

        notification_dict = {
            "patient_id": pat_int_id,
            "medical_data_level": [0] * MedicalType.get_size(),
            "medical_data_obj": med_list_obj_empty,
            "notification_level": 0,
        }
    return notification_dict


def get_patient_demographics(external_id, db_patient):
    """
    Get the patient Demographics
    """
    patient_data = {}
    patient_details = get_phi_data(db_patient["external_id"], dynamodb)
    if patient_details:
        patient_data.update(patient_details)
        patient_data["phoneNumbers"] = []
        patient_data[
            "name"
        ] = f"{patient_details.get('first_name', '')} {patient_details.get('last_name', '')}"

        patient_data["first_name"] = patient_details["first_name"]
        patient_data["last_name"] = patient_details["last_name"]
        patient_data["id"] = str(db_patient["internal_id"])
        patient_data["dbId"] = db_patient["id"]
        patient_data["picture"] = "https://weavers.space/img/default_user.jpg"
        patient_data["phoneNumbers"] = [
            {
                "title": "Cell",
                "number": f"{patient_details.get('cell_country_code', '+1')}{strip_dashes(str(patient_details.get('cell', '')))}",
            },
            {
                "title": "Home",
                "number": f"{patient_details.get('home_tel_country_code', '+1')}{strip_dashes(str(patient_details.get('home_tel', '')))}",
            },
        ]
        del patient_data["cell"]
        del patient_data["home_tel"]
    return patient_data


def get_patient_details(
    auth_user, db_patient, prv_roles=None, specialty=None, name_filter=None
):
    """
    This will called from patient_login
    Returns patient profile data for the selected patient
    """
    external_id = auth_user["userSub"]
    auth_user.update(find_user_by_external_id(cnx, external_id))
    patient_data = get_patient_demographics(external_id, db_patient)
    providers_appointment_list = get_appointment_by_internal_id(
        cnx, db_patient["internal_id"]
    )
    all_connected_users = get_connected_user_of_patient(
        cnx, db_patient["id"], prv_roles, specialty
    )
    external_ids_list = list(set([item["external_id"] for item in all_connected_users]))
    my_role = auth_user["userRole"]
    phi_data = get_phi_data_list(external_ids_list, dynamodb)
    patient_data["connectedUsers"] = []
    patient_data["internal_id"] = db_patient["internal_id"]
    for connected_user in all_connected_users:
        try:
            if auth_user["internal_id"] != connected_user["internal_id"]:
                profile_data = phi_data[connected_user["external_id"]]
                conn_user_internal_id = str(connected_user["internal_id"])
                user_data = {
                    "id": connected_user["id"],
                    "networks_id": connected_user["networks_id"],
                    "role": connected_user["role"],
                    "provider_internal_id": connected_user["internal_id"],
                    "username": profile_data["username"],
                    "office_address": profile_data.get("office_addr_1") or "",
                    "name": (
                        profile_data["first_name"] + " " + profile_data["last_name"]
                    ),
                    "first_name": profile_data["first_name"],
                    "last_name": profile_data["last_name"],
                }
                if "degree" in connected_user and connected_user["degree"] not in [
                    "",
                    None,
                    "(NONE)",
                ]:
                    user_data["name"] = (
                        user_data["name"] + ", " + connected_user["degree"]
                    )
                user_data["picture"] = "https://weavers.space/img/default_user.jpg"
                user_data["appointment_id"] = (
                    providers_appointment_list[conn_user_internal_id][0]
                    if conn_user_internal_id in providers_appointment_list
                    else ""
                )
                user_data["visit_date"] = (
                    providers_appointment_list[conn_user_internal_id][1]
                    if conn_user_internal_id in providers_appointment_list
                    else ""
                )
                user_data["phoneNumbers"] = []
                if user_data["role"] in ("physician", "nurse", "case_manager"):
                    user_data["specialty"] = connected_user["specialty"]
                    user_data["phoneNumbers"].append(
                        {
                            "title": "Office",
                            "number": f"{profile_data.get('office_tel_country_code', '+1')}{strip_dashes(str(profile_data.get('office_tel', '')))}",
                        }
                    )

                    if user_data["role"] == "physician":
                        user_data["degree"] = connected_user["degree"]
                    prv_orgs = get_user_org_ids(
                        cnx, "providers", user_id=connected_user["id"]
                    )
                    user_data["group"] = connected_user["group"]
                    user_data["organizations"] = get_org_name(cnx, prv_orgs)
                elif user_data["role"] == "caregiver":
                    user_data["phoneNumbers"].append(
                        {
                            "title": "Home",
                            "number": f"{profile_data.get('home_tel_country_code', '+1')}{strip_dashes(str(profile_data.get('home_tel', '')))}",
                        }
                    )
                    cgivers_orgs = get_user_org_ids(
                        cnx, "caregivers", user_id=connected_user["id"]
                    )
                    user_data["organizations"] = get_org_name(cnx, cgivers_orgs)
                if my_role != "caregiver":
                    user_data["phoneNumbers"].append(
                        {
                            "title": "Cell",
                            "number": f"{profile_data.get('cell_country_code', '+1')}{strip_dashes(str(profile_data.get('cell', '')))}",
                        }
                    )
                user_data_info = {}
                user_data_info["picture"] = "https://weavers.space/img/default_user.jpg"
                user_data_info["patientFirstName"] = patient_data["first_name"]
                user_data_info["patientLastName"] = patient_data["last_name"]
                user_data_info["username"] = patient_data["username"]
                user_data_info["internal_id"] = str(patient_data["internal_id"])
                patient_data["connectedUsers"].append(
                    {"user": user_data, "info": user_data_info}
                )
        except GeneralException as e:
            print(e)
    patient_data["remote_monitoring"] = db_patient["remote_monitoring"]
    if name_filter:
        connectedUsers = list(
            filter(
                lambda provider: (
                    name_filter.upper() in provider["user"]["name"].upper()
                ),
                patient_data["connectedUsers"],
            )
        )
        patient_data["connectedUsers"] = connectedUsers
    return patient_data


def list_connected_users(
    patient_data,
    all_connected_users,
    auth_user,
    phi_data,
    providers_appointment_list,
    my_role,
    patient_from_db,
    user_chat_summary,
):
    """
    Adds connected users data for connectedUsers key in patient_data input
    """
    for connected_user in all_connected_users:
        try:
            if auth_user["internal_id"] != connected_user["internal_id"]:
                profile_data = phi_data[connected_user["external_id"]]
                conn_user_internal_id = str(connected_user["internal_id"])
                user_data = {}
                user_data["id"] = connected_user["id"]
                user_data["networks_id"] = connected_user["networks_id"]
                user_data["provider_internal_id"] = connected_user["internal_id"]
                user_data["role"] = connected_user["role"]
                user_data["first_name"] = profile_data["first_name"]
                user_data["last_name"] = profile_data["last_name"]
                user_data["username"] = profile_data["username"]
                user_data["office_address"] = profile_data.get("office_addr_1") or ""
                user_data["name"] = (
                    profile_data["first_name"] + " " + profile_data["last_name"]
                )
                if "degree" in connected_user and connected_user["degree"] not in [
                    "",
                    None,
                    "(NONE)",
                ]:
                    user_data["name"] = (
                        user_data["name"] + ", " + connected_user["degree"]
                    )
                user_data["picture"] = "https://weavers.space/img/default_user.jpg"
                user_data["appointment_id"] = (
                    providers_appointment_list[conn_user_internal_id][0]
                    if conn_user_internal_id in providers_appointment_list
                    else ""
                )
                user_data["visit_date"] = (
                    providers_appointment_list[conn_user_internal_id][1]
                    if conn_user_internal_id in providers_appointment_list
                    else ""
                )
                user_data["phoneNumbers"] = []
                if user_data["role"] in ("physician", "nurse", "case_manager"):
                    user_data["specialty"] = connected_user["specialty"]
                    user_data["phoneNumbers"].append(
                        {
                            "title": "Office",
                            "number": f"{profile_data.get('office_tel_country_code', '+1')}{strip_dashes(str(profile_data.get('office_tel', '')))}",
                        }
                    )

                    if user_data["role"] == "physician":
                        user_data["degree"] = connected_user["degree"]
                    prv_orgs = get_user_org_ids(
                        cnx, "providers", user_id=connected_user["id"]
                    )
                    user_data["group"] = connected_user["group"]
                    user_data["organizations"] = get_org_name(cnx, prv_orgs)
                elif user_data["role"] == "caregiver":
                    user_data["phoneNumbers"].append(
                        {
                            "title": "Home",
                            "number": f"{profile_data.get('home_tel_country_code', '+1')}{strip_dashes(str(profile_data.get('home_tel', '')))}",
                        }
                    )
                    cgivers_orgs = get_user_org_ids(
                        cnx, "caregivers", user_id=connected_user["id"]
                    )
                    user_data["organizations"] = get_org_name(cnx, cgivers_orgs)
                if my_role != "caregiver":
                    user_data["phoneNumbers"].append(
                        {
                            "title": "Cell",
                            "number": f"{profile_data.get('cell_country_code', '+1')}{strip_dashes(str(profile_data.get('cell', '')))}",
                        }
                    )
                chat_summary_key = (
                    str(connected_user["internal_id"]),
                    str(patient_from_db["internal_id"]),
                )
                user_data_info = (
                    user_chat_summary[chat_summary_key]
                    if chat_summary_key in user_chat_summary
                    else {}
                )
                user_data_info["picture"] = "https://weavers.space/img/default_user.jpg"
                user_data_info["patientFirstName"] = patient_data["first_name"]
                user_data_info["patientLastName"] = patient_data["last_name"]
                user_data_info["username"] = patient_data["username"]
                user_data_info["internal_id"] = str(patient_data["internal_id"])
                patient_data["connectedUsers"].append(
                    {"user": user_data, "info": user_data_info}
                )
        except Exception as e:
            print(e)


def get_patient_profile(
    external_id, patient_int_id, prv_roles=None, specialty=None, name_filter=None
):
    """
    Get the patient profile for provider login
    """
    try:
        auth_user = get_user_details_from_external_id(cnx, external_id)
        my_role = auth_user["role"]
        patient_from_db = find_user_by_internal_id(cnx, patient_int_id, "patient")
        patient_data = get_patient_demographics(external_id, patient_from_db)
        provider_internal_id = auth_user["internal_id"]
        providers_appointment_list = get_appointment_by_internal_id(cnx, patient_int_id)
        user_chat_summary = summary_user_chats(cnx, auth_user, add_patient_id=True)
        all_connected_users = get_connected_user_of_patient(
            cnx, patient_from_db["id"], prv_roles, specialty
        )
        external_ids_list = list(
            set([item["external_id"] for item in all_connected_users])
        )
        phi_data = get_phi_data_list(external_ids_list, dynamodb)
        patient_data["internal_id"] = str(patient_int_id)
        patient_data["connectedUsers"] = []
        list_connected_users(
            patient_data=patient_data,
            all_connected_users=all_connected_users,
            auth_user=auth_user,
            my_role=my_role,
            patient_from_db=patient_from_db,
            phi_data=phi_data,
            providers_appointment_list=providers_appointment_list,
            user_chat_summary=user_chat_summary,
        )
        notification_dict = get_notification_level_from_network_by_id(
            cnx, auth_user["internal_id"], patient_from_db["internal_id"]
        )
        patient_data["medical_data_level"] = notification_dict["medical_data_level"]
        patient_data["medical_data_obj"] = notification_dict["medical_data_obj"]
        patient_data["notification_level"] = notification_dict["notification_level"]
        patient_data["remote_monitoring"] = patient_from_db["remote_monitoring"]
        provider_internal_id = str(auth_user["internal_id"])
        patient_data["appointment_id"] = (
            providers_appointment_list[provider_internal_id][0]
            if provider_internal_id in providers_appointment_list
            else ""
        )
        patient_data["visit_date"] = (
            providers_appointment_list[provider_internal_id][1]
            if provider_internal_id in providers_appointment_list
            else ""
        )
    except GeneralException as e:
        print(e)
    if name_filter:
        connectedUsers = list(
            filter(
                lambda provider: (
                    name_filter.upper() in provider["user"]["name"].upper()
                ),
                patient_data["connectedUsers"],
            )
        )
        patient_data["connectedUsers"] = connectedUsers
    return patient_data


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    # auth_user = get_logged_in_user(cognito_user["sub"], None)
    auth_user = event["requestContext"].get("authorizer")
    patient_internal_id = int(event["pathParameters"].get("patient_internal_id"))
    query_params = (
        event["queryStringParameters"] if event["queryStringParameters"] else {}
    )
    prv_roles = query_params.get("proles", None)
    specialty = query_params.get("specialty", None)
    name_filter = query_params.get("name_filter", None)
    if prv_roles:
        prv_roles = [x.strip() for x in prv_roles.split(",")]
    patient = find_user_by_internal_id(cnx, patient_internal_id, "patient")
    if not patient:
        status_code = 400
        result = "Patient doesn't exist"
    elif auth_user["userRole"] in ("physician", "nurse", "case_manager"):
        status_code = 200
        result = get_patient_profile(
            auth_user["userSub"], patient_internal_id, prv_roles, specialty, name_filter
        )
    else:
        result = get_patient_details(
            auth_user, patient, prv_roles, specialty, name_filter
        )
        status_code = 200
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
