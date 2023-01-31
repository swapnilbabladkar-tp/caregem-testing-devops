import json
import logging

from shared import (
    decrypt,
    get_db_connect,
    get_headers,
    read_as_dict,
)

logger = logging.getLogger(__name__)

cnx = get_db_connect()


def get_chat_messages(chat_id, cursor, limit=50):
    """
    List call chat_messages ordered by timestamp for the given chat_id
    from messages Table
    """
    query = """ SELECT * FROM messages
                WHERE chat_id = %s
                ORDER BY timestamp desc
            """
    message_list = read_as_dict(cnx, query, (chat_id))
    result = []
    if message_list:
        for msg in message_list:
            msg_dict = {}
            msg_dict["content"] = decrypt(msg["content"])
            msg_dict["critical"] = msg["critical"]
            msg_dict["read"] = msg["read"]
            msg_dict["sender_id"] = msg["sender_int_id"]
            msg_dict["timestamp"] = msg["timestamp"]
            result.append(msg_dict)
    return result


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    # auth_user = get_logged_in_user(cognito_user["sub"], None)
    # auth_user = event["requestContext"].get("authorizer")
    chat_id = event["pathParameters"].get("chat_id")
    cursor = event["queryStringParameters"].get("cursor")
    limit = event["queryStringParameters"].get("limit")
    result = get_chat_messages(chat_id, cursor, limit)
    return {"statusCode": 200, "body": json.dumps(result), "headers": get_headers()}
