import json
import logging
from datetime import datetime
from itertools import groupby

import boto3
from custom_exception import GeneralException
from medical_infor import MedicalType
from shared import (
    calculate_date_of_birth,
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data_list,
    read_as_dict,
    read_query,
    strip_dashes,
)
from sqls.patient_queries import (
    APPOINTMENT_QUERY,
    PROVIDER_NOTIFICATIONS,
    PROVIDER_PATIENT_NETWORK,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()


def get_connected_patients_of_provider(
    cnx, prv_internal_id, rm_enabled=None, codes=None
):
    """
    This function returns the list of patients
    in a provider's network for a provider
    The list is filtered if rm_enabled or codes are passed to it
    """
    j_code_assign = True if codes else None
    params = {
        "rm_enabled": rm_enabled,
        "codes": tuple(codes) if codes else tuple("NULL"),
        "internal_id": prv_internal_id,
        "j_code_assign": j_code_assign,
    }
    return read_as_dict(cnx, PROVIDER_PATIENT_NETWORK, params)


def get_notification_level_from_network(cnx, internal_id):
    """
    This function returns a list of dict with the following properties:
    1. patient_id - ID of the patient
    2. medical_data_level - list of int with level of notification in the
                            same order as ordered_list in MedicalType class
    3. medical_data_obj - list of dict with id, desc and level
                          of the notification for level data above
    4. notification_level - max notification level for the patient
    """
    notification_tuple = read_query(
        cnx, PROVIDER_NOTIFICATIONS, {"notifier_internal_id": internal_id}
    )
    notification_tuple_list = list(notification_tuple) if notification_tuple else []

    medical_data_list = [0] * MedicalType.get_size()
    # The following black magic converts the notification_tuple_list to a list of dicts in format:
    #
    #   {
    #       "patient_id": pat_id,
    #       "notification_level": {
    #           medical_data_type: notification_level,
    #           medical_data_type: notification_level,
    #           ...
    #       }
    #   }
    #
    notification_tuple_list.sort(
        key=lambda item: item[0]
    )  # sorted data is required for groupby to work correctly
    grouped_notif_list = [
        {
            "patient_id": pat_id,
            "notification_level": {
                med_index: max([flag[1] for flag in flag_list])
                for med_index, flag_list in groupby(
                    sorted(
                        [(med_type[1], med_type[2]) for med_type in med_type_tuple],
                        key=lambda item: item[0],
                    ),  # sorted data is required for groupby to work correctly
                    lambda med_type_item: med_type_item[0],
                )
            },
        }
        for pat_id, med_type_tuple in groupby(
            notification_tuple_list, lambda notif_tuple_item: notif_tuple_item[0]
        )
    ]
    notification_list = []
    for notif in grouped_notif_list:
        med_list = list(medical_data_list)
        med_list_obj = []
        for i in range(len(MedicalType.ordered_list)):
            med_list_obj.append(
                {"id": i, "desc": MedicalType.ordered_list[i], "level": 0}
            )
        level_dict = notif["notification_level"]
        for key in level_dict.keys():
            index = MedicalType.get_index(key)
            med_list[index] = level_dict[key]
            med_list_obj[index]["level"] = level_dict[key]
        notification_list.append(
            {
                "patient_id": notif["patient_id"],
                "medical_data_level": med_list,
                "medical_data_obj": med_list_obj,
                "notification_level": max(med_list),
            }
        )
    return notification_list


def get_appointment_list(cnx, pat_int_ids, prv_int_id):
    """
    This function returns a a dict with the appointment data
    for all patients of the selected provider
    The appointment dict has the patient_id as the key and
    the (appointment_id, appointment_date) tuple as value
    """
    appointment_list = read_as_dict(
        cnx,
        APPOINTMENT_QUERY,
        {"provider_internal_id": prv_int_id, "patient_id": tuple(pat_int_ids)},
    )
    appointment_dict = (
        {
            str(appointment["patient_internal_id"]): (
                str(appointment["id"]),
                appointment["date_time"].strftime("%Y-%m-%d %H:%M"),
            )
            for appointment in appointment_list
        }
        if appointment_list
        else {}
    )
    return appointment_dict


def get_patients_list(
    cnx, user, page=None, page_size=None, search_query=None, rm=None, codes=None
):
    """Get Connected patients of providers"""
    prv_int_id = user["internal_id"]
    patients = get_connected_patients_of_provider(cnx, prv_int_id, rm, codes)
    notification_list = get_notification_level_from_network(cnx, prv_int_id)
    patient_notif_dict = {
        notification["patient_id"]: notification["notification_level"]
        for notification in notification_list
    }
    results = []
    if not patients:
        return 400, "Provider Doesn't have Any patient in Network"
    pat_internal_ids = [patient["internal_id"] for patient in patients]
    external_ids = {patient["external_id"] for patient in patients}
    phi_data = get_phi_data_list(list(external_ids), dynamodb)
    patient_appointment = get_appointment_list(cnx, pat_internal_ids, prv_int_id)
    try:
        for patient in patients:
            patient_internal_id = str(patient["internal_id"])
            user_profile = phi_data[patient["external_id"]]
            dob_obj = datetime.strptime(user_profile["dob"], "%m-%d-%Y").date()
            age = calculate_date_of_birth(dob_obj)
            user_data = {
                "id": patient_internal_id,
                "first_name": user_profile["first_name"],
                "last_name": user_profile["last_name"],
                "username": user_profile["username"],
                "dob": user_profile["dob"],
                "phoneNumbers": [
                    {
                        "title": "Home",
                        "number": strip_dashes(user_profile.get("home_tel", "")),
                    },
                    {"title": "Cell", "number": strip_dashes(user.get("cell", ""))},
                ],
                "name": user_profile["first_name"] + " " + user_profile["last_name"],
                "picture": "https://weavers.space/img/default_user.jpg",
                "notification_level": patient_notif_dict[patient["internal_id"]]
                if patient["internal_id"] in patient_notif_dict
                else 0,
                "appointment_id": patient_appointment[patient_internal_id][0]
                if patient_internal_id in patient_appointment
                else "",
                "visit_date": patient_appointment[patient_internal_id][1]
                if patient_internal_id in patient_appointment
                else "",
                "remote_monitoring": patient["remote_monitoring"],
                "age": age,
            }
            results.append(user_data)
    except KeyError as err:
        logger.error(err)
        return 500, err
    except GeneralException as err:
        logger.error(err)
        return 500, err
    results = sorted(
        results, key=lambda p: (-p.get("notification_level"), p.get("last_name"))
    )
    if search_query:
        results = list(
            filter(
                lambda patient: (search_query.upper() in patient["name"].upper()),
                results,
            )
        )
    elif page and page_size:
        start_pos = int(page) * int(page_size)
        end_pos = start_pos + int(page_size)
        results = results[start_pos:end_pos]
    return 200, results


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    auth_user = event["requestContext"].get("authorizer")
    auth_user.update(
        find_user_by_external_id(
            connection, auth_user["userSub"], auth_user["userRole"]
        )
    )
    query_string = event["queryStringParameters"]
    if query_string:
        page = query_string.get("page", None)
        page_size = query_string.get("page_size", None)
        search_query = query_string.get("searchQuery", None)
        rm = query_string.get("remote_monitoring", None)
        codes = query_string.get("codes", None)
        if codes:
            codes = [x.strip() for x in codes.split(",")]
        status_code, result = get_patients_list(
            connection, auth_user, page, page_size, search_query, rm, codes
        )
    else:
        status_code, result = get_patients_list(connection, auth_user)
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
