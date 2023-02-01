import json
import logging
import os
from datetime import datetime
from http import HTTPStatus

import boto3
from custom_exception import GeneralException
import pymysql
from log_changes import get_caregiver_log_state, get_patient_log_state, log_change
from notification import insert_to_care_team_notification_table
from shared import (
    User,
    encrypt,
    find_user_by_external_id,
    find_user_by_internal_id,
    get_db_connect,
    get_headers,
    get_phi_data_from_internal_id,
    get_phi_data_list,
    get_s3_config,
    get_user_by_id,
    get_user_org_ids,
    read_as_dict,
)
from sms_util import (
    get_patient_added_to_network_message_content,
    get_phone_number_from_phi_data,
    publish_text_message,
)
from sqls.network import (
    DELETE_NETWORK_BY_ID,
    GET_ALL_PATIENT_NETWORK,
    GET_CAREGIVER_NETWORK,
    GET_CONNECTED_PATIENT_OF_USER,
    GET_EXISTING_USER_NETWORK,
    GET_EXISTING_USER_NETWORK_FOR_CAREGIVER,
    GET_ORG_DETAILS_BY_PATIENT_ID,
    GET_USER_COUNT_OF_ORG,
    INSERT_USER_TO_NETWORK,
    PATIENT_CAREGIVER_NETWORK,
    PATIENT_PROVIDER_NETWORK,
)

aws_region = os.getenv("AWSREGION")
bucket_name = os.getenv("BUCKET_NAME")
file_name = os.getenv("S3_FILE_NAME")
environment = os.getenv("ENVIRONMENT")

s3_client = boto3.client("s3", region_name=aws_region)
dynamodb = boto3.resource("dynamodb")


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
connection = get_db_connect()


def get_org_details_by_patient_id(cnx, patient_id):
    """
    Get the org_name and org_id by PATIENT_ID
    """
    return read_as_dict(cnx, GET_ORG_DETAILS_BY_PATIENT_ID, {"patient_id": patient_id})


def get_common_org_id(cnx, patient_id, user_id, role):
    """
    Get the common org id.
    :params patient_id, provider_id, cnx
    :Return common org_ids
    """
    pat_orgs = get_user_org_ids(cnx, "patients", user_id=patient_id)
    user_orgs = get_user_org_ids(cnx, role, internal_id=user_id)
    common_org = set(pat_orgs).intersection(set(user_orgs))
    if common_org:
        return list(common_org)
    return None


def get_patient_networks(cnx, patient_id, org_id):
    """
    Returns list of network users for the selected patient and org
    """
    final_list = []
    params = {"org_id": org_id, "patient_id": patient_id}
    network_providers = read_as_dict(cnx, PATIENT_PROVIDER_NETWORK, params)
    network_caregivers = read_as_dict(cnx, PATIENT_CAREGIVER_NETWORK, params)
    if network_providers:
        final_list.extend(network_providers)
    if network_caregivers:
        final_list.extend(network_caregivers)
    return HTTPStatus.OK, final_list


def get_connected_patients_of_user(cnx, user_id):
    """
    Returns list of connected patients for the input user id
    """
    try:
        patient_in_network = read_as_dict(
            cnx, GET_CONNECTED_PATIENT_OF_USER, {"user_id": user_id}
        )
        if patient_in_network:
            external_ids = [patient["external_id"] for patient in patient_in_network]
            phi_data = get_phi_data_list(external_ids)
            for patient in patient_in_network:
                user = phi_data[patient["external_id"]]
                patient["name"] = user.get("first_name") + " " + user.get("last_name")
                patient["first_name"] = user.get("first_name")
                patient["last_name"] = user.get("last_name")
                patient["role"] = "patient"
                patient["organizations"] = get_org_details_by_patient_id(
                    cnx, patient["id"]
                )
        return HTTPStatus.OK, patient_in_network
    except GeneralException as exp:
        logger.error(exp)
        return HTTPStatus.INTERNAL_SERVER_ERROR, exp


def remove_all_the_connected_networks(cnx, patient_id, org_id):
    """
    Removed all users from a patient's network for a given org
    """
    networks = read_as_dict(
        cnx, GET_ALL_PATIENT_NETWORK, {"patient_id": patient_id, "org_id": org_id}
    )
    network_ids = [item["networks_id"] for item in networks] if networks else []
    try:
        with cnx.cursor() as cursor:
            cursor.execute(DELETE_NETWORK_BY_ID, {"ids": tuple(network_ids)})
            cnx.commit()
        return HTTPStatus.OK, "Network Updated Successfully"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def check_user_belong_to_same_org(cnx, org_id, user_ids, user_type):
    """
    This function checks if the input user ids belong to the same organization
    Returns True of empty list or above condition is fulfilled
    Returns False otherwise
    """
    if user_type == "providers":
        org_table = "provider_org"
        org_column = "providers_id"
    else:
        org_table = "caregiver_org"
        org_column = "caregivers_id"
    query = GET_USER_COUNT_OF_ORG.format(
        user_type=user_type, org_table=org_table, org_column=org_column
    )
    if user_ids:
        result = read_as_dict(
            cnx, query, {"org_id": org_id, "ids": tuple(user_ids)}, fetchone=True
        )
        if isinstance(result, dict) and result["count"] == len(user_ids):
            return True
        return False
    return True


def get_user_of_same_org_not_in_list(
    cnx, provider_ids, caregiver_ids, patient_id, org_id
):
    """
    Returns list of all network users not present in new network list
    """
    provider_query = PATIENT_PROVIDER_NETWORK
    caregiver_query = PATIENT_CAREGIVER_NETWORK
    if provider_ids:
        params = {"patient_id": patient_id, "org_id": org_id, "prv_ids": provider_ids}
        provider_query += " AND providers.internal_id NOT IN %(prv_ids)s"
    else:
        params = {"patient_id": patient_id, "org_id": org_id}
    providers = read_as_dict(cnx, provider_query, params)
    provider_network_ids = (
        [item["networks_id"] for item in providers] if providers else []
    )
    if caregiver_ids:
        params = {"patient_id": patient_id, "org_id": org_id, "care_ids": caregiver_ids}
        caregiver_query += " AND caregivers.internal_id NOT IN %(care_ids)s"
    else:
        params = {"patient_id": patient_id, "org_id": org_id}
    caregivers = read_as_dict(cnx, caregiver_query, params)
    caregiver_network_ids = (
        [item["networks_id"] for item in caregivers] if caregivers else []
    )
    provider_network_ids.extend(caregiver_network_ids)

    return provider_network_ids


def get_name_from_phi_data(phi_data):
    """
    Returns name of user given user phi_data as input
    """
    return f"{phi_data['first_name']}, {phi_data['last_name']}"


def get_notification_details(
    added_member_id,
    phi_data_dict,
    added_member_internal_id_map,
    patient_data,
):
    """
    Construct notification_details string based on input data
    """
    patient_phi_data = phi_data_dict[patient_data["external_id"]]
    patient_name = get_name_from_phi_data(patient_phi_data)
    added_member_external_id = added_member_internal_id_map[added_member_id][
        "external_id"
    ]
    added_member_degree = added_member_internal_id_map[added_member_id].get("degree")
    added_member_specialty = added_member_internal_id_map[added_member_id].get(
        "specialty"
    )
    added_member_phi_data = phi_data_dict[added_member_external_id]
    added_member_name = get_name_from_phi_data(added_member_phi_data)
    if added_member_degree and added_member_specialty:
        return f"{added_member_name},{added_member_degree} {added_member_specialty} has been added to {patient_name}'s care team"
    return f"{added_member_name} has been added to {patient_name}'s care team"


def get_network_users_list_for_patient(cnx, patient_data, org_id):
    """
    Returns list of network users for the selected patient and org
    """
    status_code, result = get_patient_networks(cnx, patient_data["id"], org_id)
    if status_code == HTTPStatus.OK:
        return result
    return []


def insert_notification_for_network_providers(
    patient_data,
    users,
    added_member_internal_ids,
    auth_user,
    added_member_internal_id_map,
):
    """
    This Function:
    1. Extracts external_ids from network user list
    2. Get PHI data for all network users and patient
    3. Insert Notification regarding Careteam additions to all network users
    """
    # extract external_ids from network user list
    external_ids = [user["external_id"] for user in users]
    # append patient_external id to list
    external_ids.append(patient_data["external_id"])
    # get phi_data for all users as a dict with external_id's of users as the key
    phi_data_dict = get_phi_data_list(external_ids, dynamodb)
    current_time = datetime.utcnow()
    DEFAULT_NOTIFICATION_STATUS = 1
    DEFAULT_NOTIFICATION_LEVEL = 1
    for added_member_id in added_member_internal_ids:
        for user in users:
            # generate notification detail string for each network user
            notification_details = get_notification_details(
                added_member_id=added_member_id,
                phi_data_dict=phi_data_dict,
                added_member_internal_id_map=added_member_internal_id_map,
                patient_data=patient_data,
            )
            # insert row into care_team_notifications table for each network member
            insert_to_care_team_notification_table(
                ct_member_internal_id=added_member_id,
                patient_internal_id=patient_data["internal_id"],
                notifier_internal_id=user["internal_id"],
                level=DEFAULT_NOTIFICATION_LEVEL,
                notification_details=encrypt(notification_details),
                created_on=current_time,
                created_by=auth_user["internal_id"],
                updated_on=current_time,
                updated_by=auth_user["internal_id"],
                notification_status=DEFAULT_NOTIFICATION_STATUS,
            )
    return


def update_caregiver_network(cnx, caregiver_id, users, auth_user):
    """
    Update existing caregiver network with input user list
    """
    try:
        org_id = auth_user["userOrg"]
        caregiver = find_user_by_internal_id(cnx, caregiver_id, "caregiver")
        if not caregiver:
            return HTTPStatus.BAD_REQUEST, "Caregiver Doesn't exist"
        old_state = get_caregiver_log_state(cnx, caregiver["id"])
        if len(users) == 0:
            caregiver_network = read_as_dict(
                cnx, GET_CAREGIVER_NETWORK, {"org_id": org_id, "user_id": caregiver_id}
            )
            network_ids = (
                [item["networks_id"] for item in caregiver_network]
                if caregiver_network
                else []
            )
            if network_ids:
                with cnx.cursor() as cursor:
                    cursor.execute(DELETE_NETWORK_BY_ID, {"ids": tuple(network_ids)})
                    cnx.commit()
        else:
            patient_ids = [user["id"] for user in users]
            query = GET_CAREGIVER_NETWORK + " AND networks._patient_id NOT IN %(ids)s"
            params = {
                "ids": tuple(patient_ids),
                "user_id": caregiver_id,
                "org_id": org_id,
            }
            networks = read_as_dict(cnx, query, params)
            network_ids = [item["networks_id"] for item in networks] if networks else []
            added_patient_ids = []
            with cnx.cursor() as cursor:
                if network_ids:
                    cursor.execute(DELETE_NETWORK_BY_ID, {"ids": network_ids})
                params = {
                    "patient_ids": tuple(patient_ids),
                    "user_id": caregiver_id,
                }
                existing_networks = read_as_dict(
                    cnx, GET_EXISTING_USER_NETWORK_FOR_CAREGIVER, params
                )
                existing_networks = (
                    [item["_patient_id"] for item in existing_networks]
                    if existing_networks
                    else []
                )
                for user in users:
                    if user["id"] in existing_networks:
                        continue
                    params = {
                        "user_type": "caregiver",
                        "patient_id": user["id"],
                        "alert_receiver": 0,
                        "user_id": caregiver_id,
                    }
                    added_patient_ids.append(user["id"])
                    cursor.execute(INSERT_USER_TO_NETWORK, params)
            cnx.commit()
            with cnx.cursor() as cursor:
                for patient_id in added_patient_ids:
                    patient_data_list = get_user_by_id(cnx, patient_id, "patient")
                    patient_data: dict = (
                        patient_data_list[0] if patient_data_list else {}
                    )
                    network_users = get_network_users_list_for_patient(
                        cnx, patient_data, org_id
                    )
                    insert_notification_for_network_providers(
                        patient_data=patient_data,
                        users=network_users,
                        added_member_internal_ids=[caregiver_id],
                        auth_user=auth_user,
                        added_member_internal_id_map={caregiver_id: caregiver},
                    )
            cnx.commit()
        new_state = get_caregiver_log_state(cnx, caregiver["id"])
        caregiver["role"] = "caregiver"
        log_change(cnx, old_state, new_state, auth_user, caregiver)
        return HTTPStatus.OK, "Network Updated Successfully"
    except pymysql.MySQLError as err:
        logger.error(err)
    except GeneralException as err:
        logger.exception(err)


def get_user_ids(users):
    """
    Returns All, Provider and Caregiver internal ids as seperate lists
    """
    user_ids = []
    selected_provider_ids: list[int] = []
    selected_caregivers_ids: list[int] = []
    for user in users:
        user_ids.append(user["internal_id"])
        if User.is_provider(user["role"]):
            selected_provider_ids.append(int(user["internal_id"]))
        if user["role"] == "caregiver":
            selected_caregivers_ids.append(int(user["internal_id"]))
    return user_ids, selected_provider_ids, selected_caregivers_ids


def check_for_same_org_users(
    cnx, org_id, selected_provider_ids, selected_caregivers_ids
):
    """
    Checks if all providers and caregivers are a part of the org given as input
    """
    if not check_user_belong_to_same_org(
        cnx, org_id, selected_provider_ids, "providers"
    ):
        raise ValueError("Some users doesn't belong to your Organization!")
    if not check_user_belong_to_same_org(
        cnx, org_id, selected_caregivers_ids, "caregivers"
    ):
        raise ValueError("Some users doesn't belong to your Organization!")


def update_patient_network(cnx, patient_id, users, auth_user):
    """
    Updates existing patient network with input user list
    """
    org_id = auth_user["userOrg"]
    old_state = get_patient_log_state(cnx, patient_id)
    if len(users) == 0:
        status_code, result = remove_all_the_connected_networks(cnx, patient_id, org_id)
    else:
        user_ids, selected_provider_ids, selected_caregivers_ids = get_user_ids(users)
        check_for_same_org_users(
            cnx=cnx,
            org_id=org_id,
            selected_caregivers_ids=selected_caregivers_ids,
            selected_provider_ids=selected_provider_ids,
        )
        network_ids = get_user_of_same_org_not_in_list(
            cnx, selected_provider_ids, selected_caregivers_ids, patient_id, org_id
        )
        params = {"patient_id": patient_id, "user_ids": tuple(user_ids)}

        existing_networks = read_as_dict(cnx, GET_EXISTING_USER_NETWORK, params)
        existing_networks = (
            [item["user_internal_id"] for item in existing_networks]
            if existing_networks
            else []
        )
        added_member_internal_ids = []
        added_member_internal_id_map = {}
        s3_config = get_s3_config(bucket_name, file_name, s3_client)
        patient_added_to_network_message_content = (
            get_patient_added_to_network_message_content(
                s3_config.get(environment, {}).get("WebApp", "")
            )
        )
        patient_data_list = get_user_by_id(cnx, patient_id, "patient")
        patient_data: dict = patient_data_list[0] if patient_data_list else {}
        try:
            with cnx.cursor() as cursor:
                if network_ids:
                    cursor.execute(DELETE_NETWORK_BY_ID, {"ids": network_ids})
                for user in users:
                    if user["internal_id"] in existing_networks:
                        continue
                    added_member_internal_ids.append(user["internal_id"])
                    added_member_internal_id_map.update({user["internal_id"]: user})
                    # The alert_receiver value represents if user wishes to receive SMS communication (Caregivers will never have SMS sent to them)
                    alert_receiver = (
                        0 if user["role"] == "caregiver" else user["alert_receiver"]
                    )
                    params = {
                        "user_type": user["role"],
                        "patient_id": patient_id,
                        "alert_receiver": alert_receiver,
                        "user_id": user["internal_id"],
                    }
                    cursor.execute(INSERT_USER_TO_NETWORK, params)
                    # Check if user has set alert_receiver value to 1 and send SMS only if it is 1 (possible values are 0 or 1)
                    if alert_receiver:
                        # get phi_data of added member from DynamodDB
                        phi_data = get_phi_data_from_internal_id(
                            cnx, dynamodb, user["internal_id"], user["role"]
                        )
                        phone_number = get_phone_number_from_phi_data(phi_data)
                        # send SMS to the cell number of added member
                        try:
                            message_id = publish_text_message(
                                phone_number, patient_added_to_network_message_content
                            )
                            logger.info(f"Message sent with message ID : {message_id}")
                        except GeneralException:
                            logger.info("Failed to send Message")
                # Add Notification regarding added members to each network member
                insert_notification_for_network_providers(
                    patient_data,
                    users,
                    added_member_internal_ids,
                    auth_user,
                    added_member_internal_id_map,
                )
                cnx.commit()
            status_code = HTTPStatus.OK
            result = f"Network Updated Successfully for patient id {patient_id}"
        except pymysql.MySQLError as err:
            logger.error(err)
            return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"
        except GeneralException as exp:
            logger.exception(exp)
            return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"
    new_state = get_patient_log_state(cnx, patient_id)
    targer_user_list = get_user_by_id(cnx, patient_id, "patient")
    target_user: dict = targer_user_list[0] if targer_user_list else {}
    target_user["role"] = "patient"
    log_change(cnx, old_state, new_state, auth_user, target_user)
    return status_code, result


def lambda_handler(event, context):
    """
    Handler Function
    """
    auth_user = event["requestContext"].get("authorizer")
    identity = event["requestContext"].get("identity")
    auth_user["ipv4"] = identity.get("sourceIp", None)
    status_code = HTTPStatus.BAD_REQUEST
    result = {}
    user = find_user_by_external_id(
        connection, auth_user["userSub"], auth_user["userRole"]
    )
    auth_user.update(user)
    if event["httpMethod"] == "GET":
        user_type = event["queryStringParameters"].get("user_type")
        if auth_user.get("userOrg"):
            org_id = auth_user["userOrg"]
        else:
            patient_id = event["pathParameters"].get("user_id")
            org_id = (
                get_common_org_id(
                    connection, patient_id, user["internal_id"], auth_user["userRole"]
                )
                if user
                else None
            )
            if org_id:
                org_id = org_id[0]
                logger.info("common org id is %s", org_id)
            else:
                return HTTPStatus.NOT_FOUND, "No common org id found"
        if user_type == "patient":
            patient_id = event["pathParameters"].get("user_id")
            status_code, result = get_patient_networks(connection, patient_id, org_id)
        else:
            user_id = event["pathParameters"].get("user_id")
            status_code, result = get_connected_patients_of_user(connection, user_id)
    if event["httpMethod"] == "PUT":
        form_data = json.loads(event["body"])
        users = form_data["users"]
        if "caregiver" in event["path"].split("/"):
            caregiver_id = event["pathParameters"].get("caregiver_id")
            status_code, result = update_caregiver_network(
                connection, caregiver_id, users, auth_user
            )
        else:
            patient_id = event["pathParameters"].get("patient_id")
            status_code, result = update_patient_network(
                connection, patient_id, users, auth_user
            )
    return {
        "statusCode": status_code.value,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
