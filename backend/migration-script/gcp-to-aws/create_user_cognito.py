import logging
import os

import boto3
from botocore.exceptions import ClientError
from custom_exception import GeneralException
from dotenv import load_dotenv

load_dotenv()

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
client = boto3.client("cognito-idp", region_name="us-east-1")

user_pool_id = os.getenv("USER_POOL_ID")
aws_region = "us-east-1"


logger = logging.getLogger(__name__)


def add_users_to_cognito(uname, email):
    """
    Add user in cognito with username and email as input and a temporary password
    """
    try:
        resp = client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=uname,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "profile", "Value": "none"},
            ],
            TemporaryPassword="Caregem@123",
            MessageAction="SUPPRESS",
            ClientMetadata={"name": "admin", "org": "General", "portal": "Admin"},
        )
        cogito_user = {"username": resp["User"].get("Username")}
        cogito_user.update(
            {
                attr.get("Name"): attr.get("Value")
                for attr in resp["User"].get("Attributes")
            }
        )
        return 200, cogito_user
        # client.admin_add_user_to_group(UserPoolId=user_pool_id, Username=uname, GroupName=role)
    except client.exceptions.UsernameExistsException:
        return 106, "Username Already exists"
    except client.exceptions.InvalidParameterException:
        return 106, "Invalid email address format"
    except client.exceptions.CodeDeliveryFailureException:
        return 106, "Invalid email address format"
    except GeneralException as e:
        logger.error(e)
        raise (e)


def create_update_user_profile(user_data):
    """
    Add the User Details to Dynamo db.
    """
    try:
        table = dynamodb.Table("user_pii")
        table.put_item(Item=user_data)
        response = table.get_item(Key={"external_id": user_data["external_id"]})
        return response["Item"]
    except ClientError as err:
        logger.error(err)
        return None


def create_super_admin(uname, email, first_name, last_name):
    """
    Creates super admin user with username, email, and name as input
    """
    status_code, resp = add_users_to_cognito(uname, email)
    user_data = {
        "external_id": resp["sub"],
        "first_name": first_name,
        "last_name": last_name,
        "username": uname,
        "role": "super_admin",
    }
    return create_update_user_profile(user_data)


# Steps for setting up
# Run this function in interactive mode and call create_super_admin
# create_super_admin("sa_sanjeev", "sanjeev@carelogiq.com", "Sanjeev", "Rastogi")
# It will set with default password as mentioned in Script,
# Navigate to cognito --> App Client Settings --> Launch hosted UI
# Enter username password, and enter new password and confirm password
