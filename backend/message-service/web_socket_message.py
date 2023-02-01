import json
import logging
import os
import uuid
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from boto3.dynamodb.conditions import Key
from custom_exception import GeneralException
from notification import insert_to_message_notifications_table
from shared import (
    encrypt,
    find_user_by_external_id,
    get_db_connect,
    get_phi_data_list,
    read_as_dict,
)
from sms_util import get_phone_number_from_phi_data, publish_text_message
from sqls.chime import GET_CHANNEL_DATA, UPDATE_LATEST_MESSAGE_DETAILS

aws_region = os.getenv("AWSREGION")
user_pool_id = os.getenv("USER_POOL_ID")
chime_instance_arn = os.getenv("CHIME_INSTANCE_ARN")
ws_url = os.getenv("WEB_SOCKET_ENDPOINT_URL")

chime_client = boto3.client("chime", region_name=aws_region)
dynamo_db = boto3.resource("dynamodb", region_name=aws_region)

api_client = boto3.client("apigatewaymanagementapi", endpoint_url=ws_url)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()

DEFAULT_NOTIFICATION_STATUS = 1
DEFAULT_NOTIFICATION_LEVEL = 1


def get_member_arn(profile):
    """Return the member arn"""
    return f"{chime_instance_arn}/user/{profile}"


def get_chime_details(cnx, channel_name):
    """
    Returns dict with "channel_arn" as key and the <channel arn value> as value
    when given channel name as input
    """
    query = (
        """ SELECT channel_arn from chime_chats where channel_name = %(channel_name)s"""
    )
    chats = read_as_dict(cnx, query, {"channel_name": channel_name}, fetchone=True)
    if chats:
        return dict(chats)
    return None


def save_message_to_chime(channel_arn, content, profile):
    """Save Channel Message to Chime"""
    try:
        response = chime_client.send_channel_message(
            ChannelArn=channel_arn,
            Content=content,
            Type="STANDARD",
            Persistence="PERSISTENT",
            ClientRequestToken=str(uuid.uuid4()),
            ChimeBearer=get_member_arn(profile),
        )
        logger.info("Message Successfully Saved to chime")
        return response
    except GeneralException as err:
        logger.error(err)
        raise err


def save_last_message_to_db(cnx, content, channel_name, sender):
    """Save the last message to db"""
    params = {
        "latest_message": encrypt(content),
        "latest_message_timestamp": datetime.utcnow(),
        "latest_message_sender": sender,
        "channel_name": channel_name,
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_LATEST_MESSAGE_DETAILS, params)
        cnx.commit()
    except pymysql.MySQLError as err:
        logger.error(err)


def get_username_external_id_role_map(channel_user_info: dict):
    """
    Returns map for external_id to role of user with user_info as input
    """
    username_external_id_map = {}
    username_role_map = {}
    for key in ["user_1", "user_2", "patient"]:
        if channel_user_info[key]:
            username = channel_user_info[key].get("username", "")
            external_id = channel_user_info[key].get("external_id", "")
            role = channel_user_info[key].get("role", "")
            if username and external_id:
                username_external_id_map.update({username: external_id})
                username_role_map.update({username: role})
    return username_external_id_map, username_role_map


def get_username_internal_id_degree_map(
    cnx, username_external_id_map: dict, username_role_map: dict
):
    """
    Returns map for internal_id to degree of user with
    username_external_id map and username_role map as input
    """
    username_internal_id_map = {}
    username_degree_map = {}
    for (username, external_id) in username_external_id_map.items():
        user = find_user_by_external_id(cnx, external_id, username_role_map[username])
        if user:
            internal_id = user.get("internal_id", "")
            degree = user.get("degree", "")
            username_internal_id_map.update({username: internal_id})
            username_degree_map.update({username: degree})
    return username_internal_id_map, username_degree_map


def get_name_from_phi_data(phi_data):
    """
    Returns name of user given user phi_data as input
    """
    return f"{phi_data['first_name']}, {phi_data['last_name']}"


def get_notification_details(
    username_external_id_map,
    username_degree_map,
    sender_uname,
    patient_uname,
    is_patient_linked_channel,
    phi_data_dict,
):
    """
    Get Notification Detail String for the Notification being added.
    Currently the function assumes that only the receiver is notified
    """
    sender_data = phi_data_dict[username_external_id_map[sender_uname]]
    sender_name = get_name_from_phi_data(sender_data)
    sender_degree = username_degree_map[sender_uname]
    if is_patient_linked_channel:
        patient_data = phi_data_dict[username_external_id_map[patient_uname]]
        patient_name = get_name_from_phi_data(patient_data)
        if sender_degree:
            return f"{sender_name} {sender_degree} has sent you a message about {patient_name}"
        return f"{sender_name} has sent you a message about {patient_name}"
    if sender_degree:
        return f"{sender_name} {sender_degree} has sent you a message"
    return f"{sender_name} has sent you a message"


def get_sms_content_string(
    username_external_id_map,
    username_degree_map,
    username_role_map,
    sender_uname,
    is_patient_linked_channel,
    phi_data_dict,
):
    """
    Creates and Returns notification_details for Message Notification based on input
    """
    sender_data = phi_data_dict[username_external_id_map[sender_uname]]
    sender_name = get_name_from_phi_data(sender_data)
    sender_degree = username_degree_map[sender_uname]
    if is_patient_linked_channel:
        if sender_degree:
            return f"{sender_name} {sender_degree} has sent you a message about a patient in CareGem"
        return f"{sender_name} has sent you a message about a patient in CareGem"
    if username_role_map[sender_uname] == "patient":
        return f"{sender_name} (patient) has sent you a message in CareGem"
    if sender_degree:
        return f"{sender_name} {sender_degree} has sent you a message in CareGem"
    return f"{sender_name} has sent you a message in CareGem"


def get_receiver_phone_number(phi_data_dict, username_external_id_map, receiver_uname):
    """
    Returns phone number for user given phi_data username_external_id map
    and username of selected user as input
    """
    receiver_data = phi_data_dict[username_external_id_map[receiver_uname]]
    return get_phone_number_from_phi_data(receiver_data)


def notify_other_user(cnx, receiver_key: str, channel_name: str, message_id: str):
    """
    Inserts Message Notification for user based on input
    Sends SMS to the user regarding Message received on Caregem Portal
    """
    [receiver_uname, sender_uname] = receiver_key.split("_")
    patient_uname = channel_name.split("_")[0]
    channel_data = read_as_dict(
        cnx,
        GET_CHANNEL_DATA,
        {
            "channel_name": channel_name,
        },
        fetchone=True,
    )
    if channel_data and isinstance(channel_data, dict):
        channel_user_info: dict = json.loads(channel_data["user_info"])
        (
            username_external_id_map,
            username_role_map,
        ) = get_username_external_id_role_map(channel_user_info)
        (
            username_internal_id_map,
            username_degree_map,
        ) = get_username_internal_id_degree_map(
            cnx, username_external_id_map, username_role_map
        )
        is_patient_linked_channel = len(channel_name.split("_")) == 3
        external_id_list = list(username_external_id_map.values())
        phi_data_dict = get_phi_data_list(external_id_list, dynamo_db)
        notification_details = get_notification_details(
            username_external_id_map,
            username_degree_map,
            sender_uname,
            patient_uname,
            is_patient_linked_channel,
            phi_data_dict,
        )
        current_time = datetime.utcnow()
        insert_to_message_notifications_table(
            message_id=message_id,
            channel_name=channel_name,
            notifier_internal_id=username_internal_id_map[receiver_uname],
            receiver_internal_id=username_internal_id_map[receiver_uname],
            sender_internal_id=username_internal_id_map[sender_uname],
            level=DEFAULT_NOTIFICATION_LEVEL,
            notification_details=encrypt(notification_details),
            created_on=current_time,
            created_by=username_internal_id_map[sender_uname],
            updated_on=current_time,
            updated_by=username_internal_id_map[sender_uname],
            notification_status=DEFAULT_NOTIFICATION_STATUS,
        )
        try:
            sms_content = get_sms_content_string(
                username_external_id_map=username_external_id_map,
                is_patient_linked_channel=is_patient_linked_channel,
                phi_data_dict=phi_data_dict,
                sender_uname=sender_uname,
                username_degree_map=username_degree_map,
                username_role_map=username_role_map,
            )
            phone_number = get_receiver_phone_number(
                phi_data_dict=phi_data_dict,
                receiver_uname=receiver_uname,
                username_external_id_map=username_external_id_map,
            )
            sms_message_id = publish_text_message(phone_number, sms_content)
            logger.info(f"Message sent with message ID : {sms_message_id}")
        except Exception:
            logger.exception("Failed to send Message")
    return


def lambda_handler(event, context):
    """
    Handler function for sending message via web sockets
    """
    body = json.loads(event["body"])
    receiver_key = body.get("receiver_key")
    profile = body.get("profile")
    channel_name = body.get("channel_name")
    content = body.get("content")
    user_conn = dynamo_db.Table("user_connections")
    result = user_conn.scan(FilterExpression=Key("route_key").eq(receiver_key))
    chime_details = get_chime_details(connection, channel_name)
    if result["Items"]:
        msg_obj = {"channel_name": channel_name, "content": content}
        for item in result["Items"]:
            api_client.post_to_connection(
                ConnectionId=item["token"], Data=json.dumps(msg_obj).encode("utf-8")
            )
    if chime_details:
        response = save_message_to_chime(chime_details["channel_arn"], content, profile)
        message_id: str = response.get("MessageId", "")
        if not result.get("Items", None) and message_id:
            notify_other_user(connection, receiver_key, channel_name, message_id)

    save_last_message_to_db(
        connection, content, channel_name, receiver_key.split("_")[1]
    )
    return {
        "statusCode": HTTPStatus.OK,
        "body": json.dumps({"msg": "success"}),
    }
