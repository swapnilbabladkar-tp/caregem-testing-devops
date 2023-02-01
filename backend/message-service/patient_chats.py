import json
import logging

import boto3
from shared import (
    get_db_connect,
    get_headers,
    get_phi_data,
    get_user_by_id,
    read_as_dict,
)

logger = logging.getLogger(__name__)
dynamodb = boto3.resource("dynamodb")

cnx = get_db_connect()


def get_user_by_username(cnx, username):
    """
    Returns User data from DB based on input username
    """
    provider = """SELECT * FROM providers WHERE username = %s """
    patient = """SELECT * FROM patients WHERE username = %s """
    caregiver = """SELECT * FROM caregivers WHERE username = %s """

    user = read_as_dict(cnx, provider, (username))
    if user:
        return user, user[0]["role"]
    user = read_as_dict(cnx, patient, (username))
    if user:
        return user, "patient"
    user = read_as_dict(cnx, caregiver, (username))
    if user:
        return user, "caregiver"
    return None, None


def _sort_chats_by_last_message(chats):
    """
    Returns chats list sorted by timestamp value in reverse order
    """

    def message_timestamp_or_zero(chat_id):
        """
        lambda function callback used to return timestamp value for chat message
        Returns 0 if value not available
        """
        query = """ SELECT timestamp FROM messages
                    WHERE chat_id = %s
                    ORDER BY  timestamp DESC limit 1
                """
        with cnx.cursor() as cursor:
            cursor.execute(query, (chat_id))
            result = cursor.fetchone()
            if result:
                return int(result[0])
            return 0

    return sorted(
        chats, key=lambda chat: message_timestamp_or_zero(chat.get("id")), reverse=True
    )


def get_messages_about_patient(patient_id):
    """
    Returns Chats for the selected patient sorted in descending order by timestamp
    """
    patient_details = get_user_by_id(cnx, patient_id, "patient")[0]
    query = """ SELECT *
                FROM   chats
                WHERE  _patient_id = %s
                        OR chats.chat_id IN (SELECT chats.chat_id
                                             FROM   chats
                                             WHERE  chats.connected_user_id = %s) """
    record = (patient_id, patient_details["username"])
    chats = read_as_dict(cnx, query, record)
    result = {
        "patient": {"id": patient_id},
        "chats": [],
    }
    phi_data = get_phi_data(patient_details["external_id"], dynamodb)
    if phi_data:
        result["patient"]["name"] = phi_data["first_name"] + " " + phi_data["last_name"]
        result["patient"]["first_name"] = phi_data["first_name"]
        result["patient"]["last_name"] = phi_data["last_name"]
    if chats:
        chats_mapping = {}
        for chat in chats:
            user, participant_role = get_user_by_username(
                cnx, chat["connected_user_id"]
            )
            if user is None:
                continue
            user = user[0]
            participant = {}
            participant["internal_id"] = user["internal_id"]
            phi_data = get_phi_data(user["external_id"], dynamodb)
            if phi_data:
                participant["name"] = (
                    phi_data["first_name"] + " " + phi_data["last_name"]
                )
                participant["first_name"] = phi_data["first_name"]
                participant["last_name"] = phi_data["last_name"]
            participant["role"] = participant_role
            if chat["chat_id"] not in chats_mapping:
                chat_id = chat["chat_id"]
                chats_mapping[chat_id] = {}
                chats_mapping[chat_id]["id"] = chat["chat_id"]
                chats_mapping[chat_id]["messages"] = []
                chats_mapping[chat_id]["type"] = (
                    "private" if chat["_patient_id"] is None else "network"
                )
                chats_mapping[chat_id]["participants"] = [participant]
            else:
                chats_mapping[chat["chat_id"]]["participants"].append(participant)
        for key in chats_mapping:
            for participant in chats_mapping[key]["participants"]:
                if participant["role"] in ["patient", "caregiver"]:
                    continue
                result["chats"].append(chats_mapping[key])
    result["chats"] = _sort_chats_by_last_message(result["chats"])
    return result


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    # auth_user = get_logged_in_user(cognito_user["sub"], None)
    # auth_user = event["requestContext"].get("authorizer")
    patient_id = event["pathParameters"].get("patient_id")
    user_result = get_messages_about_patient(patient_id)
    return {
        "statusCode": 200,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
