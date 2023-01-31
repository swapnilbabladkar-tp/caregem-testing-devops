import hashlib
from http import HTTPStatus
import json
import logging
import os
from typing import Union

import boto3
from shared import (
    decrypt,
    find_role_by_internal_id,
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_linked_patient_internal_ids,
    get_secret_manager,
    read_as_dict,
)

logger = logging.getLogger(__name__)
dynamodb = boto3.resource("dynamodb")

cnx = get_db_connect()

key_object = get_secret_manager(os.getenv("ENCRYPTION_KEY_SECRET_ID"))


def get_chat_id(user1, user2, patient):
    """
    Returns hash used for chat_id based on input user ids
    """
    chat_id = [int(user1), int(user2)]

    if patient:
        chat_id.append(int(patient))
    else:
        chat_id.append(0)

    chat_id.sort()
    chat_id = "_".join(str(id) for id in chat_id)
    id_hashed = hashlib.md5(chat_id.encode("utf-8")).hexdigest()

    return id_hashed


def get_messages(external_id, role, other_user_id, about_user_id, last_time, page_size):
    """
    This Function:
    1. Gets user data for sender
    2. Creates hash used for chat_id based on the ids for
       sender, receiver and about_user(optional)
    3. Gets and returns list of messages for the generated chat_id
    """
    user = find_user_by_external_id(cnx, external_id, role)
    sender = user["internal_id"]
    chat_id = get_chat_id(sender, other_user_id, about_user_id)
    messagesQuery = """SELECT messages.id              AS messages_id,
       messages.msg_type        AS messages_msg_type,
       messages.sender_int_id   AS messages_sender_int_id,
       messages.receiver_int_id AS messages_receiver_int_id,
       messages.patient_int_id  AS messages_patient_int_id,
       messages.`action` as  messages_action,
       messages.critical        AS messages_critical,
       messages.content         AS messages_content,
       messages.timestamp       AS messages_timestamp,
       messages.chat_id         AS messages_chat_id,
       messages.`read` as    messages_read
        FROM   messages
        WHERE  messages.chat_id = %s"""
    messagesParams = chat_id

    if last_time and last_time.isdigit() and int(last_time) > 0:
        messagesQuery = messagesQuery + " AND messages.timestamp < %s"
        messagesParams = (chat_id, last_time)

    messagesQuery = messagesQuery + " ORDER BY messages.timestamp DESC"

    if page_size and page_size.isdigit() and int(page_size) > 0:
        messagesQuery = messagesQuery + " LIMIT %s"
        messagesParams = (chat_id, last_time, int(page_size))

    messages_list = read_as_dict(cnx, messagesQuery, messagesParams)

    messages_result = (
        [
            {
                "senderId": str(message["messages_sender_int_id"]),
                "content": decrypt(message["messages_content"], key_object),
                "read": message["messages_read"],
                "timestamp": int(message["messages_timestamp"]),
            }
            for message in messages_list
            if message
        ]
        if messages_list
        else []
    )

    return messages_result


def check_user_access(
    cnx, role: str, user_data: Union[dict, None], other_user_id, about_user_id
):
    is_allowed = False
    result = {}
    if role in ["physician", "nurse", "case_manager", "caregiver"] and user_data:
        patient_internal_id = about_user_id if about_user_id else other_user_id
        pat_internal_ids = get_linked_patient_internal_ids(
            cnx, user_data["internal_id"]
        )
        if int(patient_internal_id) not in pat_internal_ids:
            is_allowed = False
            result = {"message": "The patient is not a part of the provider's network"}
        else:
            is_allowed = True
            result = {"message": "Success"}
    if role == "patient" and user_data:
        other_user_role = find_role_by_internal_id(cnx, other_user_id)
        if about_user_id:
            is_allowed = False
            result = {
                "message": "You are not authorized to access another patient's data"
            }
        elif other_user_role == "patient":
            is_allowed = False
            result = {
                "message": "You are not authorized to access another patient's data"
            }
        else:
            is_allowed = True
            result = {"message": "Success"}
    return is_allowed, result


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    # auth_user = get_logged_in_user(cognito_user["sub"], None)
    auth_user = event["requestContext"].get("authorizer")
    external_id = auth_user["userSub"]
    role = auth_user["userRole"]
    user_data = find_user_by_external_id(cnx, external_id, role)
    other_user_id = event["queryStringParameters"].get("otherUserId")
    about_user_id = event["queryStringParameters"].get("about_user_id")
    last_time = event["queryStringParameters"].get("last_time")
    page_size = event["queryStringParameters"].get("page_size")
    is_allowed, access_result = check_user_access(
        cnx, role, user_data, other_user_id, about_user_id
    )
    if is_allowed and access_result and access_result["message"] == "Success":
        user_result = get_messages(
            external_id, role, other_user_id, about_user_id, last_time, page_size
        )
        status_code = HTTPStatus.OK
    else:
        status_code = HTTPStatus.BAD_REQUEST
        user_result = access_result
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
