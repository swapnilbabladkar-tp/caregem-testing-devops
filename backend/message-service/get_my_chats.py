import json
import logging
import os

import boto3
from custom_exception import GeneralException
from dotenv import load_dotenv
from shared import (
    decrypt,
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data_list,
    get_secret_manager,
    read_as_dict,
    strip_dashes,
)

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

cnx = get_db_connect()

key_object = get_secret_manager(os.getenv("ENCRYPTION_KEY_SECRET_ID"))


def get_chat_summary_base_query():
    """
    Returns base query used for getting chat summary data for a user
    from Old Chat History
    """
    query = """
            SELECT
            chat.id AS chat_id,
            chat.connected_user_id AS chat_connected_user_id,
            chat.`role` AS chat_role,
            chat.chat_id AS chat_id,
            chat._patient_id AS patientId,
            chat.internal_id AS internal_id,
            chat.external_id AS patient_external_id,
            connected_user.username AS username,
            connected_user.internal_id AS id,
            connected_user.external_id AS external_id,
            connected_user.degree As degree,
            connected_user.`role` AS role,
            connected_user.specialty AS specialty,
            msg.id AS msg_id,
            msg.msg_type AS msg_type,
            msg.sender_int_id AS sender_int_id,
            msg.receiver_int_id AS receiver_int_id,
            msg.patient_int_id AS patient_int_id,
            msg.`action` AS action,
            msg.critical AS critical,
            msg.content AS lastMessage,
            msg.timestamp AS timestamp,
            msg.chat_id AS msg_chat_id,
            msg.`read` AS `read`,
            msg.unread_count AS unreadMessages
        FROM
            (SELECT
                chats.id AS id,
                    chats.connected_user_id AS connected_user_id,
                    chats.`role` AS `role`,
                    chats.chat_id AS chat_id,
                    chats._patient_id AS _patient_id,
                    patients.internal_id AS internal_id,
                    patients.external_id AS external_id
            FROM
                chats
            LEFT OUTER JOIN patients ON chats._patient_id = patients.id
            WHERE
                chats.chat_id IN (SELECT
                        chats.chat_id
                    FROM
                        chats
                    WHERE
                        chats.connected_user_id = %s)
                    AND chats.connected_user_id != %s) AS chat
                INNER JOIN
            (SELECT
                anon_4.username AS username,
                    anon_4.internal_id AS internal_id,
                    anon_4.external_id AS external_id,
                    anon_4.`role` AS `role`,
                    anon_4.specialty AS specialty,
                    anon_4.degree AS degree
            FROM
                (SELECT
                patients.username AS username,
                    patients.internal_id AS internal_id,
                    patients.external_id AS external_id,
                    'patient' AS `role`,
                    '' AS specialty,
                    '' AS degree
            FROM
                patients UNION SELECT
                providers.username AS username,
                    providers.internal_id AS internal_id,
                    providers.external_id AS external_id,
                    providers.`role` AS `role`,
                    providers.specialty AS specialty,
                    providers.degree AS degree
            FROM
                providers UNION SELECT
                caregivers.username AS username,
                    caregivers.internal_id AS internal_id,
                    caregivers.external_id AS external_id,
                    'caregiver' AS `role`,
                    '' AS specialty,
                    '' AS degree
            FROM
                caregivers) AS anon_4) AS connected_user ON connected_user.username = chat.connected_user_id
                INNER JOIN
            (SELECT
                anon_5.id AS id,
                    anon_5.msg_type AS msg_type,
                    anon_5.sender_int_id AS sender_int_id,
                    anon_5.receiver_int_id AS receiver_int_id,
                    anon_5.patient_int_id AS patient_int_id,
                    anon_5.`action` AS `action`,
                    anon_5.critical AS critical,
                    anon_5.content AS content,
                    anon_5.timestamp AS timestamp,
                    anon_5.chat_id AS chat_id,
                    anon_5.`read` AS `read`,
                    anon_6.unread_count AS unread_count
            FROM
                (SELECT
                messages.id AS id,
                    messages.msg_type AS msg_type,
                    messages.sender_int_id AS sender_int_id,
                    messages.receiver_int_id AS receiver_int_id,
                    messages.patient_int_id AS patient_int_id,
                    messages.`action` AS `action`,
                    messages.critical AS critical,
                    messages.content AS content,
                    messages.timestamp AS timestamp,
                    messages.chat_id AS chat_id,
                    messages.`read` AS `read`
            FROM
                messages
            WHERE
                (messages.chat_id , messages.timestamp) IN (SELECT
                        messages.chat_id AS chat_id,
                            MAX(messages.timestamp) AS timestamp
                    FROM
                        messages
                    GROUP BY messages.chat_id)) AS anon_5
            LEFT OUTER JOIN (SELECT
                messages.chat_id AS chat_id,
                    COUNT(messages.`read`) AS unread_count
            FROM
                messages
            WHERE
                messages.`read` = 0
            GROUP BY messages.chat_id) AS anon_6 ON anon_5.chat_id = anon_6.chat_id) AS msg ON msg.chat_id = chat.chat_id
            ORDER BY msg.patient_int_id IS NULL,  msg.`timestamp` DESC
            """
    return query


def abbrev_specialty(specialty):
    """ "Method returns the specialty abbreviation."""
    mapping = {}
    mapping["cardiology"] = "CARD"
    mapping["cardiac EP"] = "Card EP"
    mapping["int Med"] = "IM"
    mapping["Fam Practice"] = "FP"
    mapping["neurology"] = "NEURO"
    mapping["gastroenterology"] = "GASTRO"
    mapping["gen surgery"] = "Gen Surg"
    mapping["nephrology"] = "NEPH"
    mapping["urology"] = "UROL"
    mapping["rheumatology"] = "RHEUM"
    mapping["pain mgmt"] = "PAIN MGT"
    mapping["ent"] = "ENT"
    mapping["neurosurg"] = "N-SURG"
    mapping["ophthalmology"] = "Ophthal"
    mapping["transplant surg"] = "Trans SURG"
    mapping["transplant hepatology"] = "Trans HEP"
    mapping["transplant nephrology"] = "Trans NEPH"
    mapping["hepatology"] = "HEP"
    mapping["ortho"] = "ORTHO"
    mapping["ob/gyn"] = "OB/GN"
    mapping["pediatrics"] = "PED"
    mapping["pulmonology"] = "PULM"
    mapping["endocrinology"] = "ENDO"
    mapping["interventional rad"] = "IR"
    mapping["cardiovasc surg"] = "CV SURG"
    mapping["thoracic surg"] = "Thor SURG"
    mapping["anesthesia"] = "ANES"
    mapping["plastic surg"] = "Plas SURG"
    mapping["hem/onc"] = "HEM/ONC"
    mapping["infectious dis"] = "ID"
    mapping["pm&r"] = "PM&R"
    mapping["rad onc"] = "RAD ONC"
    mapping["emergency Med"] = "EM MED"
    mapping["dermatology"] = "DERM"
    mapping["podiatry"] = "POD"
    mapping["nurse"] = "Nurse"
    mapping["Adv practice Nurse"] = "APN"
    mapping["case manager"] = "CASE MAN"
    mapping["social worker"] = "SW"

    if specialty.lower() in mapping:
        return mapping[specialty.lower()]
    return specialty


def _message_search_query_lambda(message, name_filter, prv_specialty):
    """
    Returns boolean value based on if input strings are present in the message
    The input is checked in the name, speciality and patientName
    keys in "user" property of message
    """
    user_name = (
        message["user"]["name"]
        if ("user" in message and "name" in message["user"])
        else ""
    ).upper()
    specialty = (
        message["user"]["specialty"]
        if ("user" in message and "specialty" in message["user"])
        else ""
    ).upper()
    patient_name = (
        message["info"]["patientName"]
        if ("info" in message and "patientName" in message["info"])
        else ""
    ).upper()
    if name_filter:
        name_filter = name_filter.upper()

    return (
        (name_filter in user_name)
        or (prv_specialty in specialty)
        or (name_filter in patient_name)
    )


def get_messages_for_chat_list(chat_list, external_ids_list):
    """
    Returns messages for input chat data list
    """
    messages = []
    for chat in chat_list:
        user_data = {}
        user_data["id"] = str(chat["id"])
        user_data["external_id"] = chat["external_id"]
        user_data["role"] = chat["role"]
        user_data["phoneNumbers"] = []
        external_ids_list.append(chat["external_id"])
        if chat["role"] not in ("patient", "caregiver"):
            user_data["specialty"] = abbrev_specialty(chat["specialty"])
            user_data["degree"] = chat["degree"]
        user_info = {}
        user_info["picture"] = "https://weavers.space/img/default_user.jpg"
        user_info["lastMessage"] = decrypt(chat["lastMessage"])
        user_info["timestamp"] = chat["timestamp"]
        # Only add the 'unreadMessages' if the logged user was not the sender of the last message.
        user_info["unreadMessages"] = chat["unreadMessages"]
        if chat["patientId"]:
            user_info["patientId"] = str(chat["patientId"])
            user_info["patient_external_id"] = chat["patient_external_id"]
            external_ids_list.append(chat["patient_external_id"])

        messages.append({"user": user_data, "info": user_info})
    return messages


def insert_user_data_for_messages(messages, phi_data):
    """
    Adds User data for message in message list
    """
    try:
        for message in messages:
            if (
                "patient_external_id" in message["info"]
                and message["info"]["patient_external_id"] in phi_data
            ):
                pat_user = phi_data[message["info"]["patient_external_id"]]
                message["info"]["name"] = (
                    pat_user["first_name"] + " " + pat_user["last_name"]
                )
                message["info"]["first_name"] = pat_user["first_name"]
                message["info"]["last_name"] = pat_user["last_name"]
                del message["info"]["patient_external_id"]
            if message["user"]["external_id"] in phi_data:
                user = phi_data[message["user"]["external_id"]]
                message["user"]["first_name"] = user["first_name"]
                message["user"]["last_name"] = user["last_name"]
                message["user"]["name"] = user["first_name"] + " " + user["last_name"]
                if "degree" in message["user"] and message["user"]["degree"] not in [
                    "",
                    None,
                    "(NONE)",
                ]:
                    message["user"]["degree"] = message["user"]["degree"]
                    message["user"]["name"] = (
                        message["user"]["name"] + ", " + message["user"]["degree"]
                    )
                user_role = message["user"]["role"]
                if user_role in ("physician", "nurse", "case_manager"):
                    message["user"]["phoneNumbers"].append(
                        {
                            "title": "Office",
                            "number": strip_dashes(user.get("office_tel", "")),
                        }
                    )
                elif user_role in ("patient", "caregiver"):
                    message["user"]["phoneNumbers"].append(
                        {
                            "title": "Home",
                            "number": strip_dashes(user.get("home_tel", "")),
                        }
                    )
                message["user"]["phoneNumbers"].append(
                    {"title": "Cell", "number": strip_dashes(user.get("cell", ""))}
                )
    except KeyError as err:
        logger.error(err, stack_info=True, exc_info=True)
    except GeneralException as err:
        logger.error(err, stack_info=True, exc_info=True)


def get_my_chats(
    cnx,
    username,
    page=None,
    page_size=None,
    last_time=None,
    name_filter=None,
    specialty=None,
):
    """
    Returns Chat list for logged in user along with
    user_data for the users involved in the chats
    """
    if name_filter or specialty:
        page_size = None
        page = None
    limit = ""
    query = get_chat_summary_base_query()
    params = (username, username)
    if page_size and int(page_size) > 0:
        limit = " LIMIT %s"
        params = (username, username, int(page_size))
    if page and int(page) > 0:
        limit = " LIMIT %s, %s"
        params = (username, username, int(page), int(page_size))
    if limit:
        query = query + limit
    chat_list = read_as_dict(cnx, query, params)
    external_ids_list = []
    messages = get_messages_for_chat_list(
        chat_list=chat_list, external_ids_list=external_ids_list
    )
    phi_data = get_phi_data_list(list(set(external_ids_list)))
    insert_user_data_for_messages(messages=messages, phi_data=phi_data)
    if name_filter or specialty:
        messages = list(
            filter(
                lambda message: _message_search_query_lambda(
                    message, name_filter, specialty
                ),
                messages,
            )
        )
    return messages


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    # auth_user = get_logged_in_user(cognito_user["sub"], None)
    auth_user = event["requestContext"].get("authorizer")
    queryParams = (
        event["queryStringParameters"] if event["queryStringParameters"] else {}
    )
    page = queryParams.get("page")
    page_size = queryParams.get("page_size")
    name_filter = queryParams.get("name_filter", "")
    specialty = queryParams.get("specialty", "")
    user = find_user_by_external_id(cnx, auth_user["userSub"], "providers")
    result = get_my_chats(
        cnx, user["username"], page, page_size, None, name_filter, specialty
    )
    return {"statusCode": 200, "body": json.dumps(result), "headers": get_headers()}
