import ast
import json
import logging
import os
import uuid
from http import HTTPStatus

import boto3
import pymysql
from botocore.exceptions import ClientError
from custom_exception import GeneralException
from shared import (
    User,
    decrypt,
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data,
    get_phi_data_list,
    read_as_dict,
)
from sqls.chime import (
    GET_CHANNEL_NAME,
    GET_CHANNEL_NAME_LIKE,
    GET_USER_EXTERNAL_INTERNAL_ID_LIST,
    INSERT_CHIME_CHATS,
    PROVIDER_DETAILS,
    UPDATE_CHIME_CHATS,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()

aws_region = os.getenv("AWSREGION")
user_pool_id = os.getenv("USER_POOL_ID")
chime_instance_arn = os.getenv("CHIME_INSTANCE_ARN")

cognito_client = boto3.client("cognito-idp", region_name=aws_region)
chime_client = boto3.client("chime", region_name=aws_region)
dynamodb = boto3.resource("dynamodb", region_name=aws_region)


def get_channel_name(pat, user1, user2=None):
    """Returns the channel name"""
    if user2:
        return f"{pat}_{user1}_{user2}"
    return f"{pat}_{user1}"


def query_channel_name(cnx, cname, like=False):
    """Query Db to get channel details if exists"""
    cname_list = cname.split("_")
    cname_2 = (
        get_channel_name(cname_list[0], cname_list[2], cname_list[1])
        if len(cname_list) > 2
        else ""
    )
    query = GET_CHANNEL_NAME_LIKE if like else GET_CHANNEL_NAME
    return read_as_dict(cnx, query, {"cname_1": cname, "cname_2": cname_2})


def query_channel_name_by_role(cnx, username, channel_role):
    """
    Return Channel Name based on the input username and channel_role
    from chime_chats Table
    """
    query = GET_CHANNEL_NAME_LIKE
    if channel_role:
        if len(channel_role) == 1:
            if channel_role[0] == "provider":
                conditions = "channel_role NOT LIKE " + "'%%" + "caregiver" + "%%'"
            else:
                conditions = "channel_role NOT LIKE " + "'%%" + "provider" + "%%'"
            query = query + " AND " + "(" + conditions + ")"
    return read_as_dict(cnx, query, {"cname_1": username})


def save_chat_details(
    cnx,
    channel_name,
    channel_role,
    channel_arn,
    bearer_arn,
    user_info,
    is_patient_enabled,
    created_by,
):
    """
    Save Channel Details to DB in chme_chats table
    """
    params = {
        "cname": channel_name,
        "crole": channel_role,
        "c_arn": channel_arn,
        "bearer_arn": bearer_arn,
        "user_info": json.dumps(user_info),
        "is_patient_enabled": is_patient_enabled,
        "created_by": created_by,
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_CHIME_CHATS, params)
            cnx.commit()
        return True
    except pymysql.MySQLError as err:
        logging.error(err)
        return False


def update_patient_enabled(cnx, channel_name, is_patient_enabled):
    """
    Update patient participation in the Chat Channel
    """
    is_patient_enabled = 1 if is_patient_enabled else 0
    params = {"cname": channel_name, "is_patient_enabled": is_patient_enabled}
    try:
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_CHIME_CHATS, params)
            cnx.commit()
    except pymysql.MySQLError as err:
        logger.error(err)


def get_user_details_from_cognito(uname):
    """Get User details from cognito"""
    try:
        response = cognito_client.admin_get_user(
            UserPoolId=user_pool_id, Username=uname
        )
        user_attr = response["UserAttributes"]
        user = {}
        for attr in user_attr:
            user[attr["Name"]] = attr["Value"]
        return user
    except ClientError as err:
        logging.error(err)


def get_member_arn(profile):
    """Return the member arn"""
    return f"{chime_instance_arn}/user/{profile}"


def create_channel(channel_name, logged_in_user_profile):
    """Create channel"""
    try:
        response = chime_client.create_channel(
            AppInstanceArn=chime_instance_arn,
            Mode="UNRESTRICTED",
            Privacy="PUBLIC",
            Name=channel_name,
            ClientRequestToken=str(uuid.uuid4()),
            ChimeBearer=get_member_arn(logged_in_user_profile),
        )
        return response["ChannelArn"]
    except ClientError as err:
        logging.error(err)


def list_channel_messages(channel_arn, profile, next_token=None, max_results=None):
    """ " Get the channel messages"""
    attr = {
        "ChannelArn": channel_arn,
        "SortOrder": "DESCENDING",
        "ChimeBearer": get_member_arn(profile),
    }
    if next_token:
        attr["NextToken"] = next_token
    if max_results:
        attr["MaxResults"] = int(max_results)
    try:
        response = chime_client.list_channel_messages(**attr)
        return response
    except ClientError as err:
        logger.error(err)


def delete_channel_membership(channel_arn, member_arn, chime_bearer):
    """create channel membership"""
    try:
        chime_client.delete_channel_membership(
            ChannelArn=channel_arn, MemberArn=member_arn, ChimeBearer=chime_bearer
        )
        return True, "Updated Successfully"
    except ClientError as err:
        logger.error(err)
        return False, err


def create_channel_membership(channel_arn, member_arn, chime_bearer):
    """Create channel Membership"""
    try:
        chime_client.create_channel_membership(
            ChannelArn=channel_arn,
            Type="DEFAULT",
            MemberArn=member_arn,
            ChimeBearer=chime_bearer,
        )
        return True, "Updated Successfully"
    except ClientError as err:
        logger.error(err)
        return False, err


def get_external_internal_id_dict(cnx, external_ids):
    """
    Returns external_id to internal_id mapper dict
    for patients, providers and caregivers
    """
    if external_ids:
        user_ids_list = read_as_dict(
            cnx,
            GET_USER_EXTERNAL_INTERNAL_ID_LIST,
            {"external_ids": tuple(external_ids)},
        )
        if user_ids_list:
            id_dict = {
                item["external_id"]: item["internal_id"] for item in user_ids_list
            }
            return id_dict
    return {}


def get_provider_details_from_db(cnx, external_ids):
    """
    Returns provider user_data from DB for the external_ids given as input
    The Function a dict with external_ids as key and user_data as value
    """
    if external_ids:
        providers = read_as_dict(
            cnx, PROVIDER_DETAILS, {"external_ids": tuple(external_ids)}
        )
        provider_dict = {item["external_id"]: item for item in providers}
        return provider_dict
    return {}


def create_channel_and_join_membership(auth_user, pat, user1, user2=None):
    """Create a channel and attach members"""
    channel_name = get_channel_name(pat, user1, user2)
    channel_arn = create_channel(channel_name, auth_user["profile"])
    user1_details = get_user_details_from_cognito(user1)
    user1_phi = get_phi_data(user1_details["sub"], dynamodb)
    user1_role = "provider" if User.is_provider(user1_phi["role"]) else "caregiver"
    pat_details = get_user_details_from_cognito(pat)
    pat_phi = get_phi_data(pat_details["sub"], dynamodb)
    user_info = {
        "user_1": {
            "username": user1,
            "external_id": user1_details["sub"],
            "role": user1_role,
        },
        "patient": {
            "username": pat,
            "external_id": pat_details["sub"],
            "role": pat_phi["role"],
        },
        "user_2": None,
    }
    user_list = [user1_details]
    is_patient_enabled = 0
    if user2:
        user2_details = get_user_details_from_cognito(user2)
        user2_phi = get_phi_data(user2_details["sub"], dynamodb)
        user2_role = "provider" if User.is_provider(user2_phi["role"]) else "caregiver"
        user_info["user_2"] = {
            "username": user2,
            "external_id": user2_details["sub"],
            "role": user2_role,
        }
        user_list.append(user2_details)
        channel_role = get_channel_name(pat_phi["role"], user1_role, user2_role)
    else:
        if auth_user["userRole"] == "caregiver":
            is_patient_enabled = 1
        user_list.append(pat_details)
        channel_role = get_channel_name(pat_phi["role"], user1_role)
    member_arns = [get_member_arn(user["profile"]) for user in user_list]
    try:
        chime_client.batch_create_channel_membership(
            ChannelArn=channel_arn,
            Type="DEFAULT",
            MemberArns=member_arns,
            ChimeBearer=get_member_arn(auth_user["profile"]),
        )
        db_resp = save_chat_details(
            cnx=connection,
            channel_name=channel_name,
            channel_role=channel_role,
            channel_arn=channel_arn,
            bearer_arn=get_member_arn(auth_user["profile"]),
            user_info=user_info,
            is_patient_enabled=is_patient_enabled,
            created_by=auth_user["internal_id"],
        )
        if db_resp:
            return HTTPStatus.OK, {
                "channel_arn": channel_arn,
                "channel_name": channel_name,
                "is_patient_enabled": is_patient_enabled,
            }
    except ClientError as err:
        logging.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def get_channel(cnx, auth_user, pat, user1, user2=None):
    """Get the channel if it doesn't exist create it and return channel_arns"""
    channel_name = get_channel_name(pat, user1, user2)
    channel_detail = query_channel_name(cnx, channel_name)
    if channel_detail:
        if auth_user["userRole"] == "caregiver" and user2:
            channel_detail[0]["is_patient_enabled"] = 0
        return HTTPStatus.OK, channel_detail[0]
    if auth_user["userName"] not in [user1, user2]:
        return HTTPStatus.OK, "No Chat History"
    return create_channel_and_join_membership(auth_user, pat, user1, user2)


def update_participation(
    cnx, auth_user, pat, user1, user2=None, is_patient_enabled=None
):
    """Update the patient capability to send message based on is_patient_enabled"""
    channel_name = get_channel_name(pat, user1, user2)
    channel_arn = query_channel_name(cnx, channel_name)
    if not channel_arn:
        raise GeneralException("channel_arn_does_not_exist")
    channel_arn = channel_arn[0]["channel_arn"]
    patient_detail = get_user_details_from_cognito(pat)
    if not is_patient_enabled:
        resp, msg = delete_channel_membership(
            channel_arn,
            get_member_arn(patient_detail["profile"]),
            get_member_arn(auth_user["profile"]),
        )
    else:
        resp, msg = create_channel_membership(
            channel_arn,
            get_member_arn(patient_detail["profile"]),
            get_member_arn(auth_user["profile"]),
        )
    if resp:
        update_patient_enabled(cnx, channel_name, is_patient_enabled)
        return HTTPStatus.OK, msg
    return HTTPStatus.INTERNAL_SERVER_ERROR, msg


def get_user_channel(
    cnx,
    username,
    include_patient_linked_chat=None,
    channel_role=None,
):
    """
    Returns list of channels the input username is a part of,
    along with the user_data of all users involved in the channels
    Returns:
    (User Info dict with username as key, list of channels the input user is a part of)
    Format ({"<username>":<user phi data>}, <list of channels the user is a part of> )
    """
    if channel_role:
        channel_arns = query_channel_name_by_role(cnx, username, channel_role)
    else:
        channel_arns = query_channel_name(cnx, username, like=True)
    final_channel_arns = []
    user_list = []
    for arn in channel_arns:
        participants_list = arn["channel_name"].split("_")
        arn["pat_uname"] = participants_list[0]
        arn["user1_uname"] = participants_list[1]
        arn["is_patient_linked_channel"] = 0
        user_list.append(json.loads(arn["user_info"]))
        if include_patient_linked_chat and len(participants_list) > 2:
            arn["is_patient_linked_channel"] = 1
            arn["user2_uname"] = participants_list[2]
            final_channel_arns.append(arn)
        elif len(participants_list) == 2:
            final_channel_arns.append(arn)
        del arn["user_info"]
    for arn in final_channel_arns:
        arn["latest_message"] = (
            decrypt(arn["latest_message"]) if arn.get("latest_message") else ""
        )
        arn["latest_message_timestamp"] = (
            arn["latest_message_timestamp"].strftime("%Y/%m/%d, %H:%M:%S")
            if arn.get("latest_message_timestamp")
            else ""
        )
    external_ids_list = []
    for user in user_list:
        external_ids_list.extend(
            [user["patient"]["external_id"], user["user_1"]["external_id"]]
        )
        if user["user_2"]:
            external_ids_list.append(user["user_2"]["external_id"])
    external_ids_list = list(set(external_ids_list))

    phi_data_list = get_phi_data_list(external_ids_list, dynamodb)
    provider_external_ids = [
        item["external_id"]
        for item in phi_data_list.values()
        if User.is_provider(item["role"])
    ]
    external_internal_id_dict = get_external_internal_id_dict(cnx, external_ids_list)
    provider_dict = get_provider_details_from_db(cnx, provider_external_ids)
    user_list_dict = {}
    for item in phi_data_list:
        user = phi_data_list[item]
        user["internal_id"] = str(external_internal_id_dict.get(item, ""))
        if User.is_provider(user["role"]):
            user["specialty"] = provider_dict[item]["specialty"]
            user["degree"] = provider_dict[item]["degree"]
        user_list_dict[user["username"]] = user
    return user_list_dict, final_channel_arns


def get_all_chats(
    cnx,
    auth_user,
    username,
    max_results=None,
    include_patient_linked_chat=None,
    pagination=None,
    channel_role=None,
):
    """
    Returns list of messages from all the channels the input user is a part of
    The result list if filtered based on following inputs
    1. if include_patient_linked_chat == True:
       only messages between 2 providers/caregivers
       regarding a patient will be returned
    2. max_results filters the number of messages returned from each channel
    3. Having pagination returns the next(older) set of messages based on
       the next_tokens present in the list present in the pagination argument
    4. channel_role filters the channels based on the roles of the users
       involved in the channel
    """
    if pagination is None:
        pagination = []
    user_list_dict, channel_arns = get_user_channel(
        cnx, username, include_patient_linked_chat, channel_role
    )
    message_response = []
    message_pagination = []
    pagination_dict = {item["channel_arn"]: item["next_token"] for item in pagination}
    for channel in channel_arns:
        channel_info = list_channel_messages(
            channel["channel_arn"],
            auth_user["profile"],
            pagination_dict.get(channel["channel_arn"]),
            max_results,
        )
        message_pagination.append(
            {
                "channel_arn": channel_info["ChannelArn"],
                "next_token": channel_info.get("NextToken"),
            }
        )
        channel_messages = channel_info["ChannelMessages"]
        for message in channel_messages:
            msg_obj = {}
            sender = message["Sender"]["Name"]
            if sender == channel["pat_uname"]:
                msg_obj["receiver"] = channel["user1_uname"]
            if sender == channel["user1_uname"]:
                msg_obj["receiver"] = channel["pat_uname"]
            if include_patient_linked_chat and channel.get("user2_uname", None):
                if sender == channel["user1_uname"]:
                    msg_obj["receiver"] = channel["user2_uname"]
                    msg_obj["regarding"] = channel["pat_uname"]
                if sender == channel["user2_uname"]:
                    msg_obj["receiver"] = channel["user1_uname"]
                    msg_obj["regarding"] = channel["pat_uname"]
            msg_obj["sender"] = sender
            msg_obj["content"] = message["Content"]
            msg_obj["message_id"] = message["MessageId"]
            msg_obj["created_time"] = message["CreatedTimestamp"].strftime(
                "%Y/%m/%d, %H:%M:%S"
            )
            message_response.append(msg_obj)
    return {
        "user_info": user_list_dict,
        "messages": message_response,
        "pagination": message_pagination,
    }


def get_channel_messages(cnx, channel_name, profile, next_token=None, max_results=None):
    """
    List Channel Messages
    """
    channel = query_channel_name(cnx, channel_name)
    if channel:
        channel = channel[0]
    channel_messages = list_channel_messages(
        channel["channel_arn"], profile, next_token, max_results
    )
    message_list = []
    for message_details in channel_messages["ChannelMessages"]:
        arn = {
            "latest_message": message_details["Content"],
            "latest_message_timestamp": message_details["CreatedTimestamp"].strftime(
                "%Y/%m/%d, %H:%M:%S"
            ),
            "Sender": message_details["Sender"]["Name"],
        }
        message_list.append(arn)
    return HTTPStatus.OK, {
        "next_token": channel_messages.get("NextToken"),
        "channel_arn": channel_messages["ChannelArn"],
        "messages": message_list,
    }


def lambda_handler(event, context):
    """
    Handler functions for chime
    """
    # auth_user = get_logged_in_user(cognito_user["sub"], None)
    auth_user = event["requestContext"].get("authorizer")
    query_params = event["queryStringParameters"]
    pat = query_params.get("pat", None)
    user1 = query_params.get("user1", None)
    user2 = query_params.get("user2", None)
    username = query_params.get("username", None)
    include_patient_linked_chat = (
        ast.literal_eval(query_params.get("includePatientLinkedChats"))
        if query_params.get("includePatientLinkedChats")
        else False
    )

    is_patient_enabled = (
        ast.literal_eval(query_params.get("isPatientEnabled"))
        if query_params.get("isPatientEnabled")
        else False
    )
    status_code = HTTPStatus.OK
    logged_in_user_details = find_user_by_external_id(
        connection, auth_user["userSub"], auth_user["userRole"]
    )
    auth_user["internal_id"] = logged_in_user_details["internal_id"]
    auth_user["profile"] = get_user_details_from_cognito(auth_user["userName"])[
        "profile"
    ]
    if "channel" in event["path"].split("/"):
        status_code, result = get_channel(connection, auth_user, pat, user1, user2)
    elif "patientParticipation" in event["path"].split("/"):
        status_code, result = update_participation(
            connection, auth_user, pat, user1, user2, is_patient_enabled
        )
    elif "channelMessages" in event["path"].split("/"):
        channel_name = query_params.get("channel_name", None)
        next_token = query_params.get("next_token", None)
        max_results = query_params.get("max_results", None)
        status_code, result = get_channel_messages(
            connection, channel_name, auth_user["profile"], next_token, max_results
        )
    elif "userChannel" in event["path"].split("/"):
        user_info, channel_arns = get_user_channel(
            connection,
            username,
            include_patient_linked_chat,
        )
        result = {"user_info": user_info, "channel_arns": channel_arns}
    elif "allChats" in event["path"].split("/"):
        pagination = (
            json.loads(query_params.get("pagination"))
            if query_params.get("pagination")
            else None
        )
        max_results = query_params.get("max_results")
        channel_role = query_params.get("channelRoles", None)
        if channel_role:
            channel_role = channel_role.split(",")
        result = get_all_chats(
            connection,
            auth_user,
            username,
            max_results,
            include_patient_linked_chat,
            pagination,
            channel_role,
        )
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
