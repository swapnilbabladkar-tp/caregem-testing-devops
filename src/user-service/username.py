import json
import logging
import os
import re
import unicodedata
from http import HTTPStatus
from typing import Union

import boto3
from botocore.exceptions import ClientError
from custom_exception import GeneralException
from shared import (
    find_role_by_external_id,
    get_db_connect,
    get_headers,
    get_secret_manager,
)
from user_utils import check_username_exists, generate_cognito_password

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

aws_region = os.getenv("AWSREGION")
user_pool_id = os.getenv("USER_POOL_ID")
cognito_secret_id = os.getenv("COGNITO_SECRET_ID")

client = boto3.client("cognito-idp", region_name=aws_region)

connection = get_db_connect()


class InavlidRoleException(Exception):
    """
    Exception class for Invalid Role used during Forgot Password Operation
    """


valid_role_portal_type_map = {
    "provider": "WebApp",
    "caregiver": "WebApp",
    "patient": "WebApp",
    "customer_admin": "Admin",
}


def handle_no_authorized_exception(username, portal_type):
    """
    Handler for No Authorized Exception for forgot password method in cognito
    This function resends the Welcome email for user
    """
    logger.info("Inside the handle_no_authorized_exception")
    try:
        response = client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            MessageAction="RESEND",
            TemporaryPassword=generate_cognito_password(),
            ClientMetadata={"portal": portal_type},
        )
        return response
    except GeneralException as e:
        logger.error(e)


def get_external_id_from_cognito_user(user_response: dict) -> str:
    """
    This Function:
    1. Creates dict of user attributes from input Cognito User data
    2. Returns value of "sub" attribute for user
    """
    user_attribute_dict = {}
    for item in user_response.get("UserAttributes", []):
        user_attribute_dict.update({item["Name"]: item["Value"]})
    return user_attribute_dict.get("sub", "")


def check_role_portal_permission(role: Union[str, None], portal_type: str):
    """
    This Function:
    1. Checks if input role is bot None
    2. Gets valid portal_type value for the role
    3. Checks if input portal_type is same as valid portal_type
    4. Raises InavlidRoleException if any of above conditions is false
    """
    if role and valid_role_portal_type_map.get(role) != portal_type:
        raise InavlidRoleException()


def forgot_password_admin(username, portal_type):
    """
    This Function:
    1. Calls forgot password method from cognito
    2. Handles NorAuthorizedException for the method
    3. Returns error message for other exceptions
    """
    try:
        cognito_secret = get_secret_manager(cognito_secret_id)
        user_response = client.admin_get_user(
            UserPoolId=user_pool_id, Username=username
        )
        user_external_id = get_external_id_from_cognito_user(user_response)
        role = find_role_by_external_id(connection, user_external_id)
        check_role_portal_permission(role=role, portal_type=portal_type)
        logger.info("Initiating Forgot Password Call")
        if cognito_secret:
            response = client.forgot_password(
                ClientId=cognito_secret["COGNITO_USER_CLIENT_ID"],
                Username=username,
                ClientMetadata={"portal": portal_type},
            )
            if response.get("CodeDeliveryDetails"):
                email_id = response.get("CodeDeliveryDetails")["Destination"]
                return {
                    "statusCode": HTTPStatus.OK,
                    "message": f"Email Successfully sent to {email_id}",
                }
    except client.exceptions.UserNotFoundException:
        return {
            "statusCode": HTTPStatus.BAD_REQUEST,
            "message": "Username does not exist",
        }

    except client.exceptions.InvalidParameterException:
        return {
            "statusCode": HTTPStatus.BAD_REQUEST,
            "message": f"User <{username}> is not confirmed yet",
        }

    except client.exceptions.CodeMismatchException:
        return {
            "statusCode": HTTPStatus.BAD_REQUEST,
            "message": "Invalid Verification code",
        }
    except client.exceptions.NotAuthorizedException:
        response = handle_no_authorized_exception(username, portal_type)
        return {"statusCode": HTTPStatus.OK, "message": "Email Successfully sent"}
    except InavlidRoleException:
        return {
            "statusCode": HTTPStatus.BAD_REQUEST,
            "message": "Username does not exist",
        }
    except GeneralException as e:
        return {
            "statusCode": HTTPStatus.BAD_REQUEST,
            "message": f"Unknown error {e.__str__()} ",
        }


def filter_characters(chars):
    """
    Converts the unicode chars to normal char or skips it
    Also it removes Special characters from String
    """
    chars = unicodedata.normalize("NFKD", chars).encode("ascii", "ignore")
    chars = chars.decode("utf-8")
    return "".join(e for e in chars if e.isalnum())


def get_user_name(fname, lname):
    """
    Generate Username
    1.Get the first letter of first name.
    2.Get the first 7 letter of last name.
    3.Add suffix in case of duplicates.
    """
    fname = filter_characters(fname)[0]
    lname = filter_characters(lname)[0:7]
    username = fname + lname
    username = username.lower()
    while check_username_exists(username):
        cognito_user = check_username_exists(username)
        if cognito_user:
            logger.info(cognito_user["username"])
        try:
            search_match = re.search(r"\d+", username)
            if search_match:
                suffix = int(search_match.group())
                username = re.sub(r"\d+", "", username) + str(suffix + 1)
        except AttributeError:
            username = username + str("1")
        except ClientError as err:
            logger.error(err)
    return username


def lambda_handler(event, context):
    """
    Handler function for usernames
    """
    auth_user = event["requestContext"].get("authorizer")
    result = {}
    status_code = HTTPStatus.NOT_FOUND
    if "username" in event["path"].split("/"):
        if auth_user["userRole"] in ["super_admin", "customer_admin"]:
            first_name = event["queryStringParameters"].get("first_name")
            last_name = event["queryStringParameters"].get("last_name")
            result = get_user_name(first_name, last_name)
            status_code = HTTPStatus.OK
        else:
            result = {"message": "User is not Super Admin or Customer Admin"}
            status_code = HTTPStatus.BAD_REQUEST
    elif "forgot_password" in event["path"].split("/"):
        portal_type = event["queryStringParameters"].get("portal", None)
        username = event["queryStringParameters"].get("username")
        result = forgot_password_admin(username, portal_type)
        status_code = HTTPStatus.OK
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
