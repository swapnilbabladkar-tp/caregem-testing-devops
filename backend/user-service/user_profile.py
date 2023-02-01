import json
import logging
import os

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from shared import (
    User,
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_user_org_ids,
    strip_dashes,
)
from sms_util import publish_text_message

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

aws_region = os.getenv("DYNAMODB_REGION")
user_pool_id = os.getenv("USER_POOL_ID")

dynamodb = boto3.resource("dynamodb", aws_region)

cognito_client = boto3.client("cognito-idp", region_name=aws_region)

cnx = get_db_connect()


def get_user_profile(external_id, dynamodb=None):
    """
    Fetches Profile Related Data
    """
    auth_user = {}
    if not dynamodb:
        dynamodb = boto3.resource("dynamodb", aws_region)
    table = dynamodb.Table("user_pii")
    try:
        response = table.get_item(Key={"external_id": external_id})
        if response.get("Item"):
            profile_data = response["Item"]
            if profile_data.get("org_id", ""):
                org_id = profile_data.get("org_id", "")
                if isinstance(org_id, str) or isinstance(org_id, int):
                    auth_user["userOrg"] = int(org_id)
            auth_user[
                "name"
            ] = f"{profile_data['first_name']} {profile_data['last_name']}"
            auth_user["userName"] = profile_data["username"]
            auth_user["firstName"] = profile_data["first_name"]
            auth_user["email"] = profile_data.get("email", "")
            auth_user["lastName"] = profile_data["last_name"]
            auth_user["city"] = profile_data.get("address_city", "")
            auth_user["zipCode"] = profile_data.get("address_zip", "")
            auth_user["cell"] = strip_dashes(str(profile_data.get("cell", "")))
            auth_user["gender"] = profile_data.get("gender", "")
            auth_user["home_addr_1"] = profile_data.get("home_addr_1", "")
            auth_user["dob"] = profile_data.get("dob", "")
            auth_user["role"] = profile_data.get("role", "")
            auth_user["picture"] = "https://weavers.space/img/default_user.jpg"
            auth_user["phoneNumbers"] = []
            auth_user["phoneNumbers"].append(
                {
                    "title": "Cell",
                    "number": f"{profile_data.get('cell_country_code', '')}{strip_dashes(str(profile_data.get('cell', '')))}",
                }
            )
            if auth_user["role"] in User.PROVIDER_ROLES.value:
                auth_user["phoneNumbers"].append(
                    {
                        "title": "Office",
                        "number": f"{profile_data.get('office_tel_country_code', '')}{strip_dashes(str(profile_data.get('office_tel','')))}",
                    }
                )
            else:
                auth_user["phoneNumbers"].append(
                    {
                        "title": "Home",
                        "number": f"{profile_data.get('home_tel_country_code', '')}{strip_dashes(str(profile_data.get('home_tel', '')))}",
                    }
                )
        return auth_user
    except ClientError as e:
        logging.error(e.response.get("Error", {}).get("Message", "Unknown"))


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


def auth(external_id, role, form_data):
    """
    Handles the Auth for a Given login
    """
    current_version_code = int(os.getenv("ANDROID_VERSION_CODE", "16"))
    current_build_version = int(os.getenv("IOS_BUILD_VERSION", "17"))
    min_version_code = int(os.getenv("ANDROID_FORCE_UPDATE_BELOW_VERSION_CODE", "16"))
    min_build_version = int(os.getenv("IOS_FORCE_UPDATE_BELOW_BUILD_VERSION", "17"))
    play_store_url = os.getenv("PLAY_STORE_SHORT_URL", "")
    app_store_url = os.getenv("APP_STORE_SHORT_URL", "")
    version_code = form_data.get("version_code", "")
    build_version = form_data.get("build_version", "")
    if role == "super_admin":
        super_admin_user = get_user_profile(external_id, dynamodb)
        return super_admin_user
    db_user = find_user_by_external_id(cnx, external_id, role)
    if not db_user:
        return None
    if version_code:
        if int(version_code) < int(min_version_code):
            # Send email to update the Android version of the app.
            sms_content = (
                "The version of your CAREGEM app is no longer supported. Please update as soon as possible."
                "Play Store link: {}".format(play_store_url)
            )
            logger.info(sms_content)
            publish_text_message(db_user["internal_id"], sms_content)

            # Refuse user if version code is lesser than minimum required version.
            return None

        if int(version_code) < int(current_version_code):
            # Send email to update the Android version of the app.
            # email_controller.send_update_android_app_email(authorized_user)

            # Send SMS to update the Android version of the app.
            sms_content = (
                "CARELogiQ is now CAREGEM. Please delete the CARELogiQ App and download the CAREGEM App. "
                "Play Store link: {}".format(play_store_url)
            )
            logger.info(sms_content)
            publish_text_message(db_user["internal_id"], sms_content)
            return None
    elif build_version:
        if int(build_version) < int(min_build_version):
            # Send SMS to update the iOS version of the app.
            sms_content = (
                "The version of your CAREGEM app is no longer supported. Please update as soon as possible."
                "\nApp Store link: {}".format(app_store_url)
            )
            logger.info(sms_content)
            publish_text_message(db_user["internal_id"], sms_content)

            # Refuse user if version code is lesser than minimum required version.
            return None

        if int(build_version) < int(current_build_version):
            # Send email to update the iOS version of the app.
            # email_controller.send_update_ios_app_email(authorized_user)

            # Send SMS to update the iOS version of the app.
            sms_content = (
                "CARELogiQ is now CAREGEM. Please delete the CARELogiQ App and download the CAREGEM App."
                "\nApp Store link: {}".format(app_store_url)
            )
            logger.info(sms_content)
            publish_text_message(db_user["internal_id"], sms_content)
            return None
    auth_user = get_user_profile(external_id, dynamodb)
    if auth_user and "userOrg" not in auth_user:
        auth_user["userOrg"] = get_user_org_ids(cnx, role, external_id=external_id)
    if auth_user:
        auth_user["remote_monitoring"] = db_user.get("remote_monitoring", "")
        auth_user["dbid"] = db_user["id"]
        cognito_details = get_user_details_from_cognito(auth_user["userName"])
        auth_user["profile"] = (
            cognito_details.get("profile", "") if cognito_details else ""
        )
        auth_user["internal_id"] = str(db_user["internal_id"])
        if role == "customer_admin":
            auth_user["is_read_only"] = bool(db_user["is_read_only"])
        if role in ("physician", "case_manager", "nurse"):
            auth_user["billing_permission"] = db_user["billing_permission"]
            auth_user["degree"] = db_user["degree"]
            auth_user["specialty"] = db_user["specialty"]
    return auth_user


def lambda_handler(event, context):
    """
    Handler Function
    """
    auth_user = event["requestContext"].get("authorizer")
    form_data = json.loads(event["body"])
    user_result = auth(auth_user["userSub"], auth_user["userRole"], form_data)
    if user_result:
        status_code = 200
    else:
        status_code = 400
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
