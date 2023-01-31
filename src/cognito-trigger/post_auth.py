import logging
import os

import boto3
from botocore.exceptions import ClientError
from shared import get_db_connect

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app_instance_arn = os.getenv("CHIME_INSTANCE_ARN")
aws_region = os.getenv("AWSREGION")

Chime = boto3.client("chime", aws_region)

connection = get_db_connect()


def update_locked_user(cnx, external_id):
    """
    Deletes the user from locked_user Table based on external id
    """
    query = """ DELETE FROM locked_user WHERE external_id = %(external_id)s """
    with cnx.cursor() as cursor:
        cursor.execute(query, {"external_id": external_id})
        cnx.commit()


def get_member_arn(profile):
    """Return the member arn"""
    return f"{app_instance_arn}/user/{profile}"


def describe_app_instance_user(profile):
    """
    Check if Chime App Instance User already exists for the input profile value
    Return AppInstanceUser if exists else return None
    """
    try:
        response = Chime.describe_app_instance_user(
            AppInstanceUserArn=get_member_arn(profile)
        )
        logger.info("App Instance ARN Already Exists User profile %s", profile)
        return response["AppInstanceUser"]
    except ClientError as err:
        logger.error(err)
        return None


def lambda_handler(event, context):
    """
    Lambda Handler for Post Auth Trigger Lambda in Cognito
    """
    user_name = event["userName"]
    user_attr = event["request"]["userAttributes"]
    update_locked_user(connection, user_attr["sub"])
    user_profile = user_attr["profile"]
    if user_profile == "none":
        logger.info("Profile Is not set up")
    try:
        if not describe_app_instance_user(user_profile):
            logger.info("Creating App Instance User for %s", user_name)
            response = Chime.create_app_instance_user(
                AppInstanceArn=app_instance_arn,
                AppInstanceUserId=user_profile,
                Name=user_name,
            )
            logger.info(response)
    except ClientError as err:
        logger.error(err)
        return {"statusCode": 500, "body": "Error"}
    return event
