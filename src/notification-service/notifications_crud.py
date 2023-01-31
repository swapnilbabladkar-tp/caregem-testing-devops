import json
import logging
import os
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Union

import boto3
from custom_exception import GeneralException
from shared import (
    decrypt,
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_linked_patient_internal_ids,
    get_phi_data_list,
    get_secret_manager,
    read_as_dict,
)
from sqls.notifications_sql import (
    GET_MESSAGE_NOTIFICATIONS,
    NOTIFIER_CARE_TEAM_NOTIFICATIONS_BASE_QUERY,
    NOTIFIER_MEDICATION_NOTIFICATIONS_BASE_QUERY,
    NOTIFIER_REMOTE_VITAL_NOTIFICATIONS_BASE_QUERY,
    NOTIFIER_SYMPTOM_NOTIFICATIONS_BASE_QUERY,
    PATIENT_CARE_TEAM_NOTIFICATIONS_BASE_QUERY,
    PATIENT_MEDICATION_NOTIFICATIONS_BASE_QUERY,
    PATIENT_REMOTE_VITAL_NOTIFICATIONS_BASE_QUERY,
    PATIENT_SYMPTOM_NOTIFICATIONS_BASE_QUERY,
    UPDATE_CARE_TEAM_NOTIFICATION,
    UPDATE_MEDICATION_NOTIFICATION,
    UPDATE_MESSAGE_NOTIFICATION,
    UPDATE_REMOTE_VITAL_NOTIFICATION,
    UPDATE_SYMPTOMS_NOTIFICATION,
    USER_LIST,
    GET_NOTIFIER_ID_FOR_NOTFICIATION,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")

cnx = get_db_connect()

key_object = get_secret_manager(os.getenv("ENCRYPTION_KEY_SECRET_ID"))


class NotificationListFetchException(Exception):
    """
    Exception for error in fetching Notification list for given type
    """

    def __init__(self, data):
        self.data = data


notification_types = [
    "symptoms",
    "messages",
    "remote_vitals",
    "care_team",
    "medications",
]

user_type_to_base_query_mapper = {
    "patient_symptoms": PATIENT_SYMPTOM_NOTIFICATIONS_BASE_QUERY,
    "provider_symptoms": NOTIFIER_SYMPTOM_NOTIFICATIONS_BASE_QUERY,
    "caregiver_symptoms": NOTIFIER_SYMPTOM_NOTIFICATIONS_BASE_QUERY,
    "patient_remote_vitals": PATIENT_REMOTE_VITAL_NOTIFICATIONS_BASE_QUERY,
    "provider_remote_vitals": NOTIFIER_REMOTE_VITAL_NOTIFICATIONS_BASE_QUERY,
    "caregiver_remote_vitals": NOTIFIER_REMOTE_VITAL_NOTIFICATIONS_BASE_QUERY,
    "patient_care_team": PATIENT_CARE_TEAM_NOTIFICATIONS_BASE_QUERY,
    "provider_care_team": NOTIFIER_CARE_TEAM_NOTIFICATIONS_BASE_QUERY,
    "caregiver_care_team": NOTIFIER_CARE_TEAM_NOTIFICATIONS_BASE_QUERY,
    "patient_medications": PATIENT_MEDICATION_NOTIFICATIONS_BASE_QUERY,
    "provider_medications": NOTIFIER_MEDICATION_NOTIFICATIONS_BASE_QUERY,
    "caregiver_medications": NOTIFIER_MEDICATION_NOTIFICATIONS_BASE_QUERY,
}

notification_type_table_map = {
    "symptoms": "symptom_notifications",
    "messages": "message_notifications",
    "remote_vitals": "remote_vital_notifications",
    "care_team": "care_team_notifications",
    "medications": "medication_notifications",
}


def complete_notification_query(
    input_notification_query, from_date, to_date, notification_status
):
    """
    Returns completed SQL query for notification Table based on input
    1. Adds where clause for created_on if from_date/to_date is present
    2. Adds where clause on notification_status as 0/1
       if notification_status input is read/unread respectively
    3. Adds order by clause on query to sort by created_on in desc order
    """
    notification_query = input_notification_query
    if from_date:
        notification_query = f"{notification_query} AND created_on >= %(from_date)s"
    if to_date:
        notification_query = f"{notification_query} AND created_on < %(to_date)s"
    if notification_status == "read":
        notification_query = f"{notification_query} AND notification_status = 0"
    if notification_status == "unread":
        notification_query = f"{notification_query} AND notification_status = 1"

    notification_query = f"{notification_query} ORDER BY created_on DESC"
    return notification_query


def check_user_type_and_status(user_type: Union[str, None], notification_status: str):
    """
    Checks if user_type and notification_status have valid values
    """
    if not user_type:
        return HTTPStatus.BAD_REQUEST, "user_type query param is required"
    if user_type not in ["patient", "provider", "caregiver"]:
        return HTTPStatus.BAD_REQUEST, "Invalid user_type entered"
    if notification_status not in ["read", "unread", "all"]:
        return HTTPStatus.BAD_REQUEST, "Invalid notification_status entered"
    return HTTPStatus.OK, "Success"


def get_symptoms_notification_list(
    user_internal_id,
    user_type,
    notification_status,
    input_from_date,
    input_to_date,
    logged_in_user_internal_id,
):
    """
        Returns List of symptom notifications in the Common Notification Object format
        {
        "created_on": str,
        "desc": str,
        "item_id": int, // Not the same type as for message Notification
        "notification_id": int,
        "notified_degree": str,
        "notified_internal_id": int,
        "notified_name": str,
        "patient_id": int, // Not Present in Message Notification
        "patient_name": str, // Not Present in Message Notification
        "reporter_degree": str,
        "reporter_name": str,
        "severity": int,
        "status": str,
        "type": "symptoms"
    }
    """
    result = []
    status, check_result = check_user_type_and_status(
        user_type=user_type, notification_status=notification_status
    )
    if status == HTTPStatus.BAD_REQUEST:
        return status, check_result
    try:
        from_date = (
            datetime.strptime(input_from_date, "%m/%d/%Y") if input_from_date else None
        )
        to_date = (
            datetime.strptime(input_to_date, "%m/%d/%Y") + timedelta(days=1)
            if input_to_date
            else None
        )
        params = {
            "user_internal_id": user_internal_id,
            "from_date": from_date,
            "to_date": to_date,
            "logged_in_user_internal_id": logged_in_user_internal_id,
        }
        symptoms_notification_query = user_type_to_base_query_mapper[
            f"{user_type}_symptoms"
        ]
        symptoms_notification_query = complete_notification_query(
            input_notification_query=symptoms_notification_query,
            from_date=from_date,
            notification_status=notification_status,
            to_date=to_date,
        )
        symptoms_notification_list = read_as_dict(
            cnx, symptoms_notification_query, params
        )
        user_ids = []

        if symptoms_notification_list:
            for symptoms_notification in symptoms_notification_list:
                if symptoms_notification.get("patient_internal_id"):
                    user_ids.append(str(symptoms_notification["patient_internal_id"]))
                if symptoms_notification.get("notifier_internal_id"):
                    user_ids.append(str(symptoms_notification["notifier_internal_id"]))
                if symptoms_notification.get("created_by"):
                    user_ids.append(str(symptoms_notification["created_by"]))

        unique_user_ids = list(set(user_ids))
        user_id_tuple = tuple(unique_user_ids)
        user_list = (
            read_as_dict(cnx, USER_LIST, {"user_id_string_list": user_id_tuple})
            if len(user_id_tuple)
            else []
        )
        user_dict = {}
        user_external_ids = []
        if user_list:
            for user in user_list:
                user_dict[str(user["internal_id"])] = user
                user_external_ids.append(user["external_id"])
        phi_data = get_phi_data_list(user_external_ids, dynamodb)
        if symptoms_notification_list:
            for symptoms_notification in symptoms_notification_list:
                patient_phi_data = (
                    phi_data[
                        user_dict[str(symptoms_notification["patient_internal_id"])][
                            "external_id"
                        ]
                    ]
                    if symptoms_notification.get("patient_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                provider_phi_data = (
                    phi_data[
                        user_dict[str(symptoms_notification["notifier_internal_id"])][
                            "external_id"
                        ]
                    ]
                    if symptoms_notification.get("notifier_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                notifier_degree = (
                    user_dict[str(symptoms_notification["notifier_internal_id"])].get(
                        "degree", ""
                    )
                    if symptoms_notification.get("notifier_internal_id")
                    else ""
                )
                submitter_phi_data = (
                    phi_data[
                        user_dict[str(symptoms_notification["created_by"])][
                            "external_id"
                        ]
                    ]
                    if symptoms_notification.get("created_by")
                    else {"first_name": "", "last_name": ""}
                )
                reporter_degree = (
                    user_dict[str(symptoms_notification["created_by"])].get(
                        "degree", ""
                    )
                    if symptoms_notification.get("created_by")
                    else ""
                )
                result.append(
                    {
                        "notification_id": symptoms_notification["id"],
                        "patient_id": symptoms_notification["patient_internal_id"],
                        "patient_name": f"{patient_phi_data['first_name']} {patient_phi_data['last_name']}",
                        "notified_internal_id": symptoms_notification[
                            "notifier_internal_id"
                        ],
                        "notified_name": f"{provider_phi_data['first_name']} {provider_phi_data['last_name']}",
                        "notified_degree": notifier_degree if notifier_degree else "",
                        "reporter_name": f"{submitter_phi_data['first_name']} {submitter_phi_data['last_name']}",
                        "reporter_degree": reporter_degree if reporter_degree else "",
                        "type": symptoms_notification["medical_data_type"],
                        "item_id": symptoms_notification["medical_data_id"],
                        "desc": decrypt(
                            symptoms_notification["notification_details"], key_object
                        )
                        if symptoms_notification.get("notification_details")
                        else "",
                        "status": "unread"
                        if symptoms_notification["notification_status"] == 1
                        else "read",
                        "severity": symptoms_notification["level"],
                        "created_on": symptoms_notification["created_on"].strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if symptoms_notification.get("created_on")
                        else None,
                    }
                )
        return HTTPStatus.OK, result
    except ValueError as err:
        logger.error(err)
        return HTTPStatus.BAD_REQUEST, err
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def get_user_ids_from_notifications(messages_notification_list):
    """
    Get user id list from message notification data
    """
    user_ids = []
    if messages_notification_list:
        for message_notification in messages_notification_list:
            if message_notification.get("receiver_internal_id"):
                user_ids.append(str(message_notification["receiver_internal_id"]))
            if message_notification.get("created_by"):
                user_ids.append(str(message_notification["created_by"]))
            if message_notification.get("notifier_internal_id"):
                user_ids.append(str(message_notification["notifier_internal_id"]))
            if message_notification.get("sender_internal_id"):
                user_ids.append(str(message_notification["sender_internal_id"]))
    return user_ids


def get_messages_notification_list(
    user_internal_id,
    user_type,
    notification_status,
    input_from_date,
    input_to_date,
):
    """
        Returns List of message notifications in the Message Notification format
        {
        "channel_name": str, // Not present in Common Notification Object
        "created_on": str,
        "desc": str,
        "item_id": str (symptom_id), // Not the same type as in Common Notification Object
        "notification_id": int,
        "notified_degree": str,
        "notified_internal_id": int,
        "notified_name": str,
        "receiver_degree": str, // Not present in Common Notification Object
        "receiver_internal_id": int, // Not present in Common Notification Object
        "receiver_name": str, // Not present in Common Notification Object
        "reporter_degree": str,
        "reporter_name": str,
        "sender_degree": str, // Not present in Common Notification Object
        "sender_internal_id": int, // Not present in Common Notification Object
        "sender_name": str, // Not present in Common Notification Object
        "severity": int,
        "status": str,
        "type": "messages"
    }
    """
    result = []
    status, check_result = check_user_type_and_status(
        user_type=user_type, notification_status=notification_status
    )
    if status == HTTPStatus.BAD_REQUEST:
        return status, check_result
    try:
        from_date = (
            datetime.strptime(input_from_date, "%m/%d/%Y") if input_from_date else None
        )
        to_date = (
            datetime.strptime(input_to_date, "%m/%d/%Y") + timedelta(days=1)
            if input_to_date
            else None
        )

        params = {
            "user_internal_id": user_internal_id,
            "from_date": from_date,
            "to_date": to_date,
        }

        messages_notification_query = GET_MESSAGE_NOTIFICATIONS

        messages_notification_query = complete_notification_query(
            input_notification_query=messages_notification_query,
            from_date=from_date,
            notification_status=notification_status,
            to_date=to_date,
        )

        messages_notification_list = read_as_dict(
            cnx, messages_notification_query, params
        )

        user_ids = get_user_ids_from_notifications(messages_notification_list)

        unique_user_ids = list(set(user_ids))
        user_id_tuple = tuple(unique_user_ids)

        user_list = (
            read_as_dict(cnx, USER_LIST, {"user_id_string_list": user_id_tuple})
            if len(user_id_tuple)
            else []
        )

        user_dict = {}
        user_external_ids = []
        if user_list:
            for user in user_list:
                user_dict[str(user["internal_id"])] = user
                user_external_ids.append(user["external_id"])

        phi_data = get_phi_data_list(user_external_ids, dynamodb)
        if messages_notification_list:
            for message_notification in messages_notification_list:
                notifier_phi_data = (
                    phi_data[
                        user_dict[str(message_notification["notifier_internal_id"])][
                            "external_id"
                        ]
                    ]
                    if message_notification.get("notifier_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                notifier_degree = (
                    user_dict[str(message_notification["notifier_internal_id"])].get(
                        "degree", ""
                    )
                    if message_notification.get("notifier_internal_id")
                    else ""
                )
                receiver_phi_data = (
                    phi_data[
                        user_dict[str(message_notification["receiver_internal_id"])][
                            "external_id"
                        ]
                    ]
                    if message_notification.get("receiver_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                receiver_degree = (
                    user_dict[str(message_notification["receiver_internal_id"])].get(
                        "degree", ""
                    )
                    if message_notification.get("receiver_internal_id")
                    else ""
                )
                sender_phi_data = (
                    phi_data[
                        user_dict[str(message_notification["sender_internal_id"])][
                            "external_id"
                        ]
                    ]
                    if message_notification.get("sender_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                sender_degree = (
                    user_dict[str(message_notification["sender_internal_id"])].get(
                        "degree", ""
                    )
                    if message_notification.get("sender_internal_id")
                    else ""
                )
                reporter_phi_data = (
                    phi_data[
                        user_dict[str(message_notification["created_by"])][
                            "external_id"
                        ]
                    ]
                    if message_notification.get("created_by")
                    else {"first_name": "", "last_name": ""}
                )
                reporter_degree = (
                    user_dict[str(message_notification["created_by"])].get("degree", "")
                    if message_notification.get("created_by")
                    else ""
                )
                result.append(
                    {
                        "notification_id": message_notification["id"],
                        "notified_internal_id": message_notification[
                            "notifier_internal_id"
                        ],
                        "notified_name": f"{notifier_phi_data['first_name']} {notifier_phi_data['last_name']}",
                        "notified_degree": notifier_degree if notifier_degree else "",
                        "receiver_internal_id": message_notification[
                            "receiver_internal_id"
                        ],
                        "receiver_name": f"{receiver_phi_data['first_name']} {receiver_phi_data['last_name']}",
                        "receiver_degree": receiver_degree if receiver_degree else "",
                        "sender_internal_id": message_notification[
                            "sender_internal_id"
                        ],
                        "sender_name": f"{sender_phi_data['first_name']} {sender_phi_data['last_name']}",
                        "sender_degree": sender_degree if sender_degree else "",
                        "reporter_name": f"{reporter_phi_data['first_name']} {reporter_phi_data['last_name']}",
                        "reporter_degree": reporter_degree if reporter_degree else "",
                        "type": "messages",
                        "channel_name": message_notification["channel_name"],
                        "item_id": message_notification["message_id"],
                        "desc": decrypt(
                            message_notification["notification_details"], key_object
                        )
                        if message_notification.get("notification_details")
                        else "",
                        "status": "unread"
                        if message_notification["notification_status"] == 1
                        else "read",
                        "severity": message_notification["level"],
                        "created_on": message_notification["created_on"].strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if message_notification.get("created_on")
                        else None,
                    }
                )

        return HTTPStatus.OK, result
    except ValueError as err:
        logger.error(err)
        return HTTPStatus.BAD_REQUEST, err
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def get_remote_vitals_notification_list(
    user_internal_id,
    user_type,
    notification_status,
    input_from_date,
    input_to_date,
    logged_in_user_internal_id,
):
    """
        Returns List of remote vitals notifications in the Common Notification Object format
        {
        "created_on": str,
        "desc": str,
        "item_id": int, // Not the same type as for message Notification
        "notification_id": int,
        "notified_degree": str,
        "notified_internal_id": int,
        "notified_name": str,
        "patient_id": int, // Not Present in Message Notification
        "patient_name": str, // Not Present in Message Notification
        "reporter_degree": str,
        "reporter_name": str,
        "severity": int,
        "status": str,
        "type": "remote_vitals"
    }
    """
    result = []
    status, check_result = check_user_type_and_status(
        user_type=user_type, notification_status=notification_status
    )
    if status == HTTPStatus.BAD_REQUEST:
        return status, check_result
    try:
        from_date = (
            datetime.strptime(input_from_date, "%m/%d/%Y") if input_from_date else None
        )
        to_date = (
            datetime.strptime(input_to_date, "%m/%d/%Y") + timedelta(days=1)
            if input_to_date
            else None
        )
        params = {
            "user_internal_id": user_internal_id,
            "from_date": from_date,
            "to_date": to_date,
            "logged_in_user_internal_id": logged_in_user_internal_id,
        }
        remote_vitals_notification_query = user_type_to_base_query_mapper[
            f"{user_type}_remote_vitals"
        ]
        remote_vitals_notification_query = complete_notification_query(
            input_notification_query=remote_vitals_notification_query,
            from_date=from_date,
            notification_status=notification_status,
            to_date=to_date,
        )
        remote_vitals_notification_list = read_as_dict(
            cnx, remote_vitals_notification_query, params
        )
        user_ids = []

        if remote_vitals_notification_list:
            for remote_vitals_notification in remote_vitals_notification_list:
                if remote_vitals_notification.get("patient_internal_id"):
                    user_ids.append(
                        str(remote_vitals_notification["patient_internal_id"])
                    )
                if remote_vitals_notification.get("notifier_internal_id"):
                    user_ids.append(
                        str(remote_vitals_notification["notifier_internal_id"])
                    )
                if remote_vitals_notification.get("created_by"):
                    user_ids.append(str(remote_vitals_notification["created_by"]))

        unique_user_ids = list(set(user_ids))
        user_id_tuple = tuple(unique_user_ids)
        user_list = (
            read_as_dict(cnx, USER_LIST, {"user_id_string_list": user_id_tuple})
            if len(user_id_tuple)
            else []
        )
        user_dict = {}
        user_external_ids = []
        if user_list:
            for user in user_list:
                user_dict[str(user["internal_id"])] = user
                user_external_ids.append(user["external_id"])
        phi_data = get_phi_data_list(user_external_ids, dynamodb)
        if remote_vitals_notification_list:
            for remote_vitals_notification in remote_vitals_notification_list:
                patient_phi_data = (
                    phi_data[
                        user_dict[
                            str(remote_vitals_notification["patient_internal_id"])
                        ]["external_id"]
                    ]
                    if remote_vitals_notification.get("patient_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                provider_phi_data = (
                    phi_data[
                        user_dict[
                            str(remote_vitals_notification["notifier_internal_id"])
                        ]["external_id"]
                    ]
                    if remote_vitals_notification.get("notifier_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                notifier_degree = (
                    user_dict[
                        str(remote_vitals_notification["notifier_internal_id"])
                    ].get("degree", "")
                    if remote_vitals_notification.get("notifier_internal_id")
                    else ""
                )
                submitter_phi_data = (
                    phi_data[
                        user_dict[str(remote_vitals_notification["created_by"])][
                            "external_id"
                        ]
                    ]
                    if remote_vitals_notification.get("created_by")
                    else {"first_name": "", "last_name": ""}
                )
                reporter_degree = (
                    user_dict[str(remote_vitals_notification["created_by"])].get(
                        "degree", ""
                    )
                    if remote_vitals_notification.get("created_by")
                    else ""
                )
                result.append(
                    {
                        "notification_id": remote_vitals_notification["id"],
                        "patient_id": remote_vitals_notification["patient_internal_id"],
                        "patient_name": f"{patient_phi_data['first_name']} {patient_phi_data['last_name']}",
                        "notified_internal_id": remote_vitals_notification[
                            "notifier_internal_id"
                        ],
                        "notified_name": f"{provider_phi_data['first_name']} {provider_phi_data['last_name']}",
                        "notified_degree": notifier_degree if notifier_degree else "",
                        "reporter_name": f"{submitter_phi_data['first_name']} {submitter_phi_data['last_name']}",
                        "reporter_degree": reporter_degree if reporter_degree else "",
                        "type": "remote_vitals",
                        "item_id": remote_vitals_notification["remote_vital_id"],
                        "desc": decrypt(
                            remote_vitals_notification["notification_details"],
                            key_object,
                        )
                        if remote_vitals_notification.get("notification_details")
                        else "",
                        "status": "unread"
                        if remote_vitals_notification["notification_status"] == 1
                        else "read",
                        "severity": remote_vitals_notification["level"],
                        "created_on": remote_vitals_notification["created_on"].strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if remote_vitals_notification.get("created_on")
                        else None,
                    }
                )
        return HTTPStatus.OK, result
    except ValueError as err:
        logger.error(err)
        return HTTPStatus.BAD_REQUEST, err
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def get_care_team_notification_list(
    user_internal_id,
    user_type,
    notification_status,
    input_from_date,
    input_to_date,
    logged_in_user_internal_id,
):
    """
        Returns List of care team notifications in the Common Notification Object format
        {
        "created_on": str,
        "desc": str,
        "item_id": int, // Not the same type as for message Notification
        "notification_id": int,
        "notified_degree": str,
        "notified_internal_id": int,
        "notified_name": str,
        "patient_id": int, // Not Present in Message Notification
        "patient_name": str, // Not Present in Message Notification
        "reporter_degree": str,
        "reporter_name": str,
        "severity": int,
        "status": str,
        "type": "care_team"
    }
    """
    result = []
    status, check_result = check_user_type_and_status(
        user_type=user_type, notification_status=notification_status
    )
    if status == HTTPStatus.BAD_REQUEST:
        return status, check_result
    try:
        from_date = (
            datetime.strptime(input_from_date, "%m/%d/%Y") if input_from_date else None
        )
        to_date = (
            datetime.strptime(input_to_date, "%m/%d/%Y") + timedelta(days=1)
            if input_to_date
            else None
        )
        params = {
            "user_internal_id": user_internal_id,
            "from_date": from_date,
            "to_date": to_date,
            "logged_in_user_internal_id": logged_in_user_internal_id,
        }
        care_team_notification_query = user_type_to_base_query_mapper[
            f"{user_type}_care_team"
        ]
        care_team_notification_query = complete_notification_query(
            input_notification_query=care_team_notification_query,
            from_date=from_date,
            notification_status=notification_status,
            to_date=to_date,
        )
        care_team_notification_list = read_as_dict(
            cnx, care_team_notification_query, params
        )
        user_ids = []

        if care_team_notification_list:
            for care_team_notification in care_team_notification_list:
                if care_team_notification.get("patient_internal_id"):
                    user_ids.append(str(care_team_notification["patient_internal_id"]))
                if care_team_notification.get("notifier_internal_id"):
                    user_ids.append(str(care_team_notification["notifier_internal_id"]))
                if care_team_notification.get("created_by"):
                    user_ids.append(str(care_team_notification["created_by"]))

        unique_user_ids = list(set(user_ids))
        user_id_tuple = tuple(unique_user_ids)
        user_list = (
            read_as_dict(cnx, USER_LIST, {"user_id_string_list": user_id_tuple})
            if len(user_id_tuple)
            else []
        )
        user_dict = {}
        user_external_ids = []
        if user_list:
            for user in user_list:
                user_dict[str(user["internal_id"])] = user
                user_external_ids.append(user["external_id"])
        phi_data = get_phi_data_list(user_external_ids, dynamodb)
        if care_team_notification_list:
            for care_team_notification in care_team_notification_list:
                patient_phi_data = (
                    phi_data[
                        user_dict[str(care_team_notification["patient_internal_id"])][
                            "external_id"
                        ]
                    ]
                    if care_team_notification.get("patient_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                provider_phi_data = (
                    phi_data[
                        user_dict[str(care_team_notification["notifier_internal_id"])][
                            "external_id"
                        ]
                    ]
                    if care_team_notification.get("notifier_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                notifier_degree = (
                    user_dict[str(care_team_notification["notifier_internal_id"])].get(
                        "degree", ""
                    )
                    if care_team_notification.get("notifier_internal_id")
                    else ""
                )
                submitter_phi_data = (
                    phi_data[
                        user_dict[str(care_team_notification["created_by"])][
                            "external_id"
                        ]
                    ]
                    if care_team_notification.get("created_by")
                    else {"first_name": "", "last_name": ""}
                )
                reporter_degree = (
                    user_dict[str(care_team_notification["created_by"])].get(
                        "degree", ""
                    )
                    if care_team_notification.get("created_by")
                    else ""
                )
                result.append(
                    {
                        "notification_id": care_team_notification["id"],
                        "patient_id": care_team_notification["patient_internal_id"],
                        "patient_name": f"{patient_phi_data['first_name']} {patient_phi_data['last_name']}",
                        "notified_internal_id": care_team_notification[
                            "notifier_internal_id"
                        ],
                        "notified_name": f"{provider_phi_data['first_name']} {provider_phi_data['last_name']}",
                        "notified_degree": notifier_degree if notifier_degree else "",
                        "reporter_name": f"{submitter_phi_data['first_name']} {submitter_phi_data['last_name']}",
                        "reporter_degree": reporter_degree if reporter_degree else "",
                        "type": "care_team",
                        "item_id": care_team_notification["ct_member_internal_id"],
                        "desc": decrypt(care_team_notification["notification_details"])
                        if care_team_notification.get("notification_details")
                        else "",
                        "status": "unread"
                        if care_team_notification["notification_status"] == 1
                        else "read",
                        "severity": care_team_notification["level"],
                        "created_on": care_team_notification["created_on"].strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if care_team_notification.get("created_on")
                        else None,
                    }
                )
        return HTTPStatus.OK, result
    except ValueError as err:
        logger.error(err)
        return HTTPStatus.BAD_REQUEST, err
    except GeneralException as err:
        logger.exception(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def get_medications_notification_list(
    user_internal_id,
    user_type,
    notification_status,
    input_from_date,
    input_to_date,
    logged_in_user_internal_id,
):
    """
        Returns List of symptom notifications in the Common Notification Object format
        {
        "created_on": str,
        "desc": str,
        "item_id": int, // Not the same type as for message Notification
        "notification_id": int,
        "notified_degree": str,
        "notified_internal_id": int,
        "notified_name": str,
        "patient_id": int, // Not Present in Message Notification
        "patient_name": str, // Not Present in Message Notification
        "reporter_degree": str,
        "reporter_name": str,
        "severity": int,
        "status": str,
        "type": "medications"
    }
    """
    result = []
    status, check_result = check_user_type_and_status(
        user_type=user_type, notification_status=notification_status
    )
    if status == HTTPStatus.BAD_REQUEST:
        return status, check_result
    try:
        from_date = (
            datetime.strptime(input_from_date, "%m/%d/%Y") if input_from_date else None
        )
        to_date = (
            datetime.strptime(input_to_date, "%m/%d/%Y") + timedelta(days=1)
            if input_to_date
            else None
        )
        params = {
            "user_internal_id": user_internal_id,
            "from_date": from_date,
            "to_date": to_date,
            "logged_in_user_internal_id": logged_in_user_internal_id,
        }
        medications_notification_query = user_type_to_base_query_mapper[
            f"{user_type}_medications"
        ]
        medications_notification_query = complete_notification_query(
            input_notification_query=medications_notification_query,
            from_date=from_date,
            notification_status=notification_status,
            to_date=to_date,
        )
        medications_notification_list = read_as_dict(
            cnx, medications_notification_query, params
        )
        user_ids = []
        if medications_notification_list:
            for medications_notification in medications_notification_list:
                if medications_notification.get("patient_internal_id"):
                    user_ids.append(
                        str(medications_notification["patient_internal_id"])
                    )
                if medications_notification.get("notifier_internal_id"):
                    user_ids.append(
                        str(medications_notification["notifier_internal_id"])
                    )
                if medications_notification.get("created_by"):
                    user_ids.append(str(medications_notification["created_by"]))

        unique_user_ids = list(set(user_ids))
        user_id_tuple = tuple(unique_user_ids)
        user_list = (
            read_as_dict(cnx, USER_LIST, {"user_id_string_list": user_id_tuple})
            if len(user_id_tuple)
            else []
        )
        user_dict = {}
        user_external_ids = []
        if user_list:
            for user in user_list:
                user_dict[str(user["internal_id"])] = user
                user_external_ids.append(user["external_id"])
        phi_data = get_phi_data_list(user_external_ids, dynamodb)
        if medications_notification_list:
            for medications_notification in medications_notification_list:
                patient_phi_data = (
                    phi_data[
                        user_dict[str(medications_notification["patient_internal_id"])][
                            "external_id"
                        ]
                    ]
                    if medications_notification.get("patient_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                provider_phi_data = (
                    phi_data[
                        user_dict[
                            str(medications_notification["notifier_internal_id"])
                        ]["external_id"]
                    ]
                    if medications_notification.get("notifier_internal_id")
                    else {"first_name": "", "last_name": ""}
                )
                notifier_degree = (
                    user_dict[
                        str(medications_notification["notifier_internal_id"])
                    ].get("degree", "")
                    if medications_notification.get("notifier_internal_id")
                    else ""
                )
                submitter_phi_data = (
                    phi_data[
                        user_dict[str(medications_notification["created_by"])][
                            "external_id"
                        ]
                    ]
                    if medications_notification.get("created_by")
                    else {"first_name": "", "last_name": ""}
                )
                reporter_degree = (
                    user_dict[str(medications_notification["created_by"])].get(
                        "degree", ""
                    )
                    if medications_notification.get("created_by")
                    else ""
                )
                result.append(
                    {
                        "notification_id": medications_notification["id"],
                        "patient_id": medications_notification["patient_internal_id"],
                        "patient_name": f"{patient_phi_data['first_name']} {patient_phi_data['last_name']}",
                        "notified_internal_id": medications_notification[
                            "notifier_internal_id"
                        ],
                        "notified_name": f"{provider_phi_data['first_name']} {provider_phi_data['last_name']}",
                        "notified_degree": notifier_degree if notifier_degree else "",
                        "reporter_name": f"{submitter_phi_data['first_name']} {submitter_phi_data['last_name']}",
                        "reporter_degree": reporter_degree if reporter_degree else "",
                        "type": "medications",
                        "item_id": medications_notification["medication_row_id"],
                        "desc": decrypt(
                            medications_notification["notification_details"]
                        )
                        if medications_notification.get("notification_details")
                        else "",
                        "status": "unread"
                        if medications_notification["notification_status"] == 1
                        else "read",
                        "severity": medications_notification["level"],
                        "created_on": medications_notification["created_on"].strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        if medications_notification.get("created_on")
                        else None,
                    }
                )
        return HTTPStatus.OK, result
    except ValueError as err:
        logger.error(err)
        return HTTPStatus.BAD_REQUEST, err
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def get_role_based_notification_types(logged_in_user_role):
    """
    Returns subset of Notification Types list based on input role
    """
    if logged_in_user_role == "patient":
        return ["messages"]
    return notification_types


def update_notification_list_result(
    notification_type, status_code, notification_list_result, final_result
):
    if status_code == HTTPStatus.OK:
        logger.info("Successfully listed %s notifications" % (notification_type))
        final_result.update({notification_type: notification_list_result})
    else:
        final_result = {"message": notification_list_result}
        raise NotificationListFetchException(final_result)
    return final_result


def get_notifications_list(
    user_id,
    user_type,
    notification_status,
    from_date,
    to_date,
    logged_in_user_internal_id,
    logged_in_user_role,
):
    """
    Returns dict with notification type as key and list of notifications as value
    Format:
    {
        "symptoms": [<symptom notifications>],
        "remote_vitals": [<remote_vitals notifications>]
        "care_team": [<care_team notifications>]
        "messages": [<messages notifications>],
        "medications": [<medications notifications>]
    }
    """
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    result = {type: [] for type in notification_types}
    role_notification_types = get_role_based_notification_types(logged_in_user_role)
    try:
        for type in role_notification_types:
            if type == "symptoms":
                status_code, symptom_result = get_symptoms_notification_list(
                    user_id,
                    user_type,
                    notification_status,
                    from_date,
                    to_date,
                    logged_in_user_internal_id,
                )
                result = update_notification_list_result(
                    notification_type=type,
                    status_code=status_code,
                    notification_list_result=symptom_result,
                    final_result=result,
                )
            if type == "messages":
                status_code, message_result = get_messages_notification_list(
                    user_id, user_type, notification_status, from_date, to_date
                )
                result = update_notification_list_result(
                    notification_type=type,
                    status_code=status_code,
                    notification_list_result=message_result,
                    final_result=result,
                )
            if type == "remote_vitals":
                (
                    status_code,
                    remote_vitals_result,
                ) = get_remote_vitals_notification_list(
                    user_id,
                    user_type,
                    notification_status,
                    from_date,
                    to_date,
                    logged_in_user_internal_id,
                )
                result = update_notification_list_result(
                    notification_type=type,
                    status_code=status_code,
                    notification_list_result=remote_vitals_result,
                    final_result=result,
                )
            if type == "care_team":
                status_code, care_team_result = get_care_team_notification_list(
                    user_id,
                    user_type,
                    notification_status,
                    from_date,
                    to_date,
                    logged_in_user_internal_id,
                )
                result = update_notification_list_result(
                    notification_type=type,
                    status_code=status_code,
                    notification_list_result=care_team_result,
                    final_result=result,
                )
            if type == "medications":
                status_code, medications_result = get_medications_notification_list(
                    user_id,
                    user_type,
                    notification_status,
                    from_date,
                    to_date,
                    logged_in_user_internal_id,
                )
                result = update_notification_list_result(
                    notification_type=type,
                    status_code=status_code,
                    notification_list_result=medications_result,
                    final_result=result,
                )
    except NotificationListFetchException as error:
        result = error.data
    return status_code, result


def update_symptom_notification_status(
    notification_id, notification_new_status, logged_in_user_internal_id
):
    """
    Updates Symptom Notification Status based on input notification id
    """
    try:
        current_time = datetime.utcnow()
        notification_status_int = 0 if (notification_new_status == "read") else 1
        with cnx.cursor() as cursor:
            cursor.execute(
                UPDATE_SYMPTOMS_NOTIFICATION,
                {
                    "notification_status": notification_status_int,
                    "notification_id": notification_id,
                    "logged_in_user_internal_id": logged_in_user_internal_id,
                    "current_time": current_time,
                },
            )
            cnx.commit()
            return HTTPStatus.OK, "Success"
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def update_message_notification_status(
    notification_id, notification_new_status, logged_in_user_internal_id
):
    """
    Updates Message Notification Status based on input notification id
    """
    try:
        current_time = datetime.utcnow()
        notification_status_int = 0 if (notification_new_status == "read") else 1
        with cnx.cursor() as cursor:
            cursor.execute(
                UPDATE_MESSAGE_NOTIFICATION,
                {
                    "notification_status": notification_status_int,
                    "notification_id": notification_id,
                    "logged_in_user_internal_id": logged_in_user_internal_id,
                    "current_time": current_time,
                },
            )
            cnx.commit()
            return HTTPStatus.OK, "Success"
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def update_remote_vitals_notification_status(
    notification_id, notification_new_status, logged_in_user_internal_id
):
    """
    Updates Remote Vitals Notification Status based on input notification id
    """
    try:
        current_time = datetime.utcnow()
        notification_status_int = 0 if (notification_new_status == "read") else 1
        with cnx.cursor() as cursor:
            cursor.execute(
                UPDATE_REMOTE_VITAL_NOTIFICATION,
                {
                    "notification_status": notification_status_int,
                    "notification_id": notification_id,
                    "logged_in_user_internal_id": logged_in_user_internal_id,
                    "current_time": current_time,
                },
            )
            cnx.commit()
            return HTTPStatus.OK, "Success"
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def update_care_team_notification_status(
    notification_id, notification_new_status, logged_in_user_internal_id
):
    """
    Updates Care Team Notification Status based on input notification id
    """
    try:
        current_time = datetime.utcnow()
        notification_status_int = 0 if (notification_new_status == "read") else 1
        with cnx.cursor() as cursor:
            cursor.execute(
                UPDATE_CARE_TEAM_NOTIFICATION,
                {
                    "notification_status": notification_status_int,
                    "notification_id": notification_id,
                    "logged_in_user_internal_id": logged_in_user_internal_id,
                    "current_time": current_time,
                },
            )
            cnx.commit()
            return HTTPStatus.OK, "Success"
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def update_medications_notification_status(
    notification_id, notification_new_status, logged_in_user_internal_id
):
    """
    Updates Medication Notification Status based on input notification id
    """
    try:
        current_time = datetime.utcnow()
        notification_status_int = 0 if (notification_new_status == "read") else 1
        with cnx.cursor() as cursor:
            cursor.execute(
                UPDATE_MEDICATION_NOTIFICATION,
                {
                    "notification_status": notification_status_int,
                    "notification_id": notification_id,
                    "logged_in_user_internal_id": logged_in_user_internal_id,
                    "current_time": current_time,
                },
            )
            cnx.commit()
            return HTTPStatus.OK, "Success"
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def update_notification_status(
    notification_id,
    notification_new_status,
    notification_type,
    logged_in_user_internal_id,
):
    """
    This function calls the update function for the notification status based on type
    """
    if notification_new_status is None:
        return HTTPStatus.BAD_REQUEST, "status is required"
    if notification_new_status not in ["read", "unread"]:
        return HTTPStatus.BAD_REQUEST, "status is invalid. valid values are read/unread"
    if notification_type is None:
        return HTTPStatus.BAD_REQUEST, "type is required"
    if notification_type == "symptoms":
        return update_symptom_notification_status(
            notification_id, notification_new_status, logged_in_user_internal_id
        )
    if notification_type == "messages":
        return update_message_notification_status(
            notification_id, notification_new_status, logged_in_user_internal_id
        )
    if notification_type == "remote_vitals":
        return update_remote_vitals_notification_status(
            notification_id, notification_new_status, logged_in_user_internal_id
        )
    if notification_type == "care_team":
        return update_care_team_notification_status(
            notification_id, notification_new_status, logged_in_user_internal_id
        )
    if notification_type == "medications":
        return update_medications_notification_status(
            notification_id, notification_new_status, logged_in_user_internal_id
        )
    return (
        HTTPStatus.BAD_REQUEST,
        f"invalid type value. valid values are {'/'.join(notification_types)}",
    )


def check_list_user_access(
    role: str, logged_in_user_internal_id, user_id, user_type: str
):
    is_allowed = False
    result = {}
    if role == "patient":
        if str(user_id) == str(logged_in_user_internal_id) and user_type == "patient":
            is_allowed = True
            result = {"message": "Success"}
        else:
            is_allowed = False
            result = {"message": "You are not authorized to access another user's data"}
    if role in ["physician", "nurse", "case_manager", "caregiver"]:
        pat_internal_ids = get_linked_patient_internal_ids(
            cnx, logged_in_user_internal_id
        )
        if (
            str(user_id) == str(logged_in_user_internal_id)
            and user_type in ["provider", "caregiver"]
        ) or (int(user_id) in pat_internal_ids and user_type == "patient"):
            is_allowed = True
            result = {"message": "Success"}
        else:
            is_allowed = False
            result = {"message": "You are not authorized to access another user's data"}
    return is_allowed, result


def check_update_user_access(
    cnx, logged_in_user_internal_id, notification_id, notification_type
):
    is_allowed = False
    result = {}
    get_notifier_id_for_notification = GET_NOTIFIER_ID_FOR_NOTFICIATION.format(
        notification_type_table_map[notification_type]
    )
    notification_data = read_as_dict(
        cnx,
        get_notifier_id_for_notification,
        {"notification_id": notification_id},
        fetchone=True,
    )
    if notification_data and isinstance(notification_data, dict):
        notifier_internal_id = notification_data["notifier_internal_id"]
        if notifier_internal_id and str(notifier_internal_id) == str(
            logged_in_user_internal_id
        ):
            is_allowed = True
            result = {"message": "Success"}
        else:
            result = {
                "message": "You are not allowed to change notification status for another user"
            }
    if not notification_data:
        result = {"message": "Notification not found"}
    return is_allowed, result


def lambda_handler(event, context):
    """
    Handler Function
    """
    auth_user = event["requestContext"].get("authorizer")
    external_id = auth_user["userSub"]
    logged_in_user_role = auth_user["userRole"]
    auth_user.update(find_user_by_external_id(cnx, external_id))
    logged_in_user_internal_id = auth_user["internal_id"]
    api_response = {
        "statusCode": HTTPStatus.BAD_REQUEST,
        "body": json.dumps("Invalid API call"),
        "headers": get_headers(),
    }
    if event["httpMethod"] == "GET":
        status_code = HTTPStatus.NOT_FOUND
        result = {}
        user_id = event["pathParameters"].get("user_id")
        query_string = event["queryStringParameters"]
        user_type = query_string.get("user_type", None)
        notification_status = query_string.get("notification_status", "all")
        from_date = query_string.get("from_date", None)
        to_date = query_string.get("to_date", None)
        is_allowed, access_result = check_list_user_access(
            logged_in_user_internal_id=logged_in_user_internal_id,
            role=logged_in_user_role,
            user_id=user_id,
            user_type=user_type,
        )
        if is_allowed and access_result and access_result["message"] == "Success":
            status_code, result = get_notifications_list(
                user_id,
                user_type,
                notification_status,
                from_date,
                to_date,
                logged_in_user_internal_id,
                logged_in_user_role,
            )
        else:
            status_code = HTTPStatus.BAD_REQUEST
            result = access_result
        api_response = {
            "statusCode": status_code,
            "body": json.dumps(result),
            "headers": get_headers(),
        }

    elif event["httpMethod"] == "PUT":
        notification_id = event["pathParameters"].get("notification_id")
        req_body = json.loads(event["body"])
        notification_new_status = req_body["status"] if "status" in req_body else None
        notification_type = req_body["type"] if "type" in req_body else None
        is_allowed, access_result = check_update_user_access(
            cnx,
            logged_in_user_internal_id=logged_in_user_internal_id,
            notification_id=notification_id,
            notification_type=notification_type,
        )
        if is_allowed and access_result and access_result["message"] == "Success":
            status_code, result = update_notification_status(
                notification_id,
                notification_new_status,
                notification_type,
                logged_in_user_internal_id,
            )
        else:
            status_code = HTTPStatus.BAD_REQUEST
            result = access_result
        api_response = {
            "statusCode": status_code,
            "body": json.dumps(result),
            "headers": get_headers(),
        }
    return api_response
