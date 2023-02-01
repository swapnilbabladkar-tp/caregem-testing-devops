import json
import logging
import os

import boto3
from botocore.exceptions import ClientError
from custom_exception import GeneralException
from shared import (
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_org_name,
    get_phi_data,
    get_phi_data_list,
    read_as_dict,
    strip_dashes,
)
from sqls.provider_data import (
    CHANNEL_NAME_LIKE,
    GET_APPOINTMENT,
    GET_PROVIDER,
    PATIENT_SHARED_PROVIDERS,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

chime_instance_arn = os.getenv("CHIME_INSTANCE_ARN")
aws_region = os.getenv("AWSREGION")
user_pool_id = os.getenv("USER_POOL_ID")

dynamodb = boto3.resource("dynamodb", region_name=aws_region)
chime_client = boto3.client("chime", region_name=aws_region)
cognito_client = boto3.client("cognito-idp", region_name=aws_region)

connection = get_db_connect()


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


def get_channel_arns(cnx, prv_uname):
    """
    Returns dict with channel_name as key and arn as value for the channels
    with the input username as a member
    """
    result = read_as_dict(cnx, CHANNEL_NAME_LIKE, {"cname": prv_uname})
    return (
        {item["channel_name"]: item["channel_arn"] for item in result} if result else {}
    )


def get_last_sent_messages(channel_arn, profile):
    """Get the channel messages"""
    profile = f"{chime_instance_arn}/user/{profile}"
    attr = {
        "ChannelArn": channel_arn,
        "SortOrder": "DESCENDING",
        "ChimeBearer": profile,
        "MaxResults": 1,
    }
    try:
        message_details = chime_client.list_channel_messages(**attr).get(
            "ChannelMessages"
        )
        if message_details:
            message_details = message_details[0]
            msg = {
                "lastMessage": message_details["Content"],
                "timestamp": int(
                    round(message_details["CreatedTimestamp"].timestamp())
                ),
            }
            return msg
        return {}
    except ClientError as err:
        logger.error(err)


def get_appointment_by_internal_id(cnx, pat_int_id, prv_int_id):
    """
    Get Appointment By Internal ID
    """
    return read_as_dict(
        cnx,
        GET_APPOINTMENT,
        {"patient_id": pat_int_id, "provider_id": prv_int_id},
        fetchone=True,
    )


def patients_shared_providers(cnx, user, prv, name_filter=None):
    """
    Patients Shared with Providers
    """
    patients = read_as_dict(
        cnx,
        PATIENT_SHARED_PROVIDERS,
        {"logged_in_user_id": user["internal_id"], "user_id": prv["id"]},
    )
    if not patients:
        return []
    external_ids_list = list(set([item["external_id"] for item in patients]))
    phi_data = get_phi_data_list(external_ids_list, dynamodb)
    channel_dict = get_channel_arns(cnx, prv["username"])
    try:
        for pat in patients:
            profile_data = phi_data[pat["external_id"]]
            pat["patientName"] = (
                profile_data["first_name"] + " " + profile_data["last_name"]
            )
            prv_appointment_dict = get_appointment_by_internal_id(
                cnx, pat["patientId"], prv["id"]
            )
            pat["picture"] = "https://weavers.space/img/default_user.jpg"
            pat["username"] = profile_data["username"]
            pat["phoneNumbers"] = [
                {
                    "title": "Home",
                    "number": f"{profile_data.get('home_tel_country_code', '')}{strip_dashes(profile_data.get('home_tel', ''))}",
                },
                {
                    "title": "Cell",
                    "number": f"{profile_data.get('cell_country_code', '')}{strip_dashes(profile_data.get('cell',''))}",
                },
            ]
            if prv_appointment_dict:
                pat["appointment_id"] = prv_appointment_dict["id"]
                pat["visit_date"] = prv_appointment_dict["date_time"].strftime(
                    "%Y-%m-%d %H:%M"
                )
            else:
                pat["appointment_id"] = pat["visit_date"] = ""
            channel_name = f'{pat["username"]}_{user["username"]}_{prv["username"]}'
            if channel_name in channel_dict:
                pat["messages"] = get_last_sent_messages(
                    channel_dict[channel_name], user["profile"]
                )
            else:
                pat["messages"] = {}
            del pat["external_id"]
    except GeneralException as err:
        logger.error(err)
    if name_filter:
        patients = list(
            filter(
                lambda patient: (name_filter.upper() in patient["patientName"].upper()),
                patients,
            )
        )
    return patients


def get_provider_profile(cnx, user, provider_id, name_filter=None):
    """
    Get the providers profile.
    """
    prv = read_as_dict(cnx, GET_PROVIDER, {"provider_id": provider_id}, fetchone=True)
    if not prv:
        return []
    phi_data = get_phi_data(prv["external_id"], dynamodb)
    if phi_data:
        prv["username"] = phi_data["username"]
        provider_orgs = get_org_name(cnx, prv["org_ids"].split(","))
        return {
            "id": prv["id"],
            "degree": prv["degree"],
            "group": prv["group"],
            "role": prv["role"],
            "specialty": prv["specialty"],
            "username": phi_data["username"],
            "picture": "https://weavers.space/img/default_user.jpg",
            "addressCity": phi_data.get("address_city") or "",
            "addressZip": phi_data.get("address_zip") or "",
            "name": f"{phi_data.get('first_name')} {phi_data.get('last_name')}",
            "first_name": phi_data.get("first_name"),
            "last_name": phi_data.get("last_name"),
            "officeAddr1": phi_data.get("office_addr_1") or "",
            "state": phi_data.get("state") or "",
            "internal_id": str(provider_id),
            "phoneNumbers": [
                {
                    "title": "Office",
                    "number": f"{phi_data.get('office_tel_country_code', '')}{strip_dashes(str(phi_data.get('office_tel', '')))}",
                },
                {
                    "title": "cell phone",
                    "number": f"{phi_data.get('cell_country_code', '')}{strip_dashes(str(phi_data.get('cell', '')))}",
                },
            ],
            "patients": patients_shared_providers(cnx, user, prv, name_filter),
            "orgs": [item["name"] for item in provider_orgs] if provider_orgs else [],
        }


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    auth_user = event["requestContext"].get("authorizer")
    provider_id = int(event["pathParameters"].get("provider_id"))
    query_params = (
        event["queryStringParameters"] if event["queryStringParameters"] else {}
    )
    name_filter = query_params.get("name_filter", None)
    user = find_user_by_external_id(connection, auth_user["userSub"], "providers")
    if user:
        user["username"] = auth_user["userName"]
        user_details = get_user_details_from_cognito(user["username"])
        if user_details:
            user["profile"] = user_details["profile"]
    result = get_provider_profile(connection, user, provider_id, name_filter)
    return {
        "statusCode": 200,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
