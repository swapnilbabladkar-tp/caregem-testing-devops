import logging
import os

import boto3
from email_template import ChangeUserEmail, PasswordChangeEmail, WelcomeEmail
from shared import get_s3_config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


aws_region = os.getenv("AWSREGION")
bucket_name = os.getenv("BUCKET_NAME")
file_name = os.getenv("S3_FILE_NAME")
environment = os.getenv("ENVIRONMENT")

s3_client = boto3.client("s3", region_name=aws_region)


def get_welcome_email_template(event, url):
    """
    Get the welcome email
    """
    user_metadata = event["request"]["clientMetadata"]
    name = user_metadata.get("name", "")
    org_name = user_metadata.get("org", "")
    welcome_email = WelcomeEmail(org_name, name, url)
    event["response"]["emailSubject"] = welcome_email.subject()
    event["response"]["emailMessage"] = welcome_email.render()
    return event


def get_forgot_email_template(event, url):
    """
    Forgot Password.
    """
    username = event["userName"]
    passwd_change_email = PasswordChangeEmail(username, url)
    event["response"]["emailSubject"] = passwd_change_email.subject()
    event["response"]["emailMessage"] = passwd_change_email.render()
    return event


def send_code_verify_email(event, url):
    """
    Update User Attributes
    """
    username = event["userName"]
    change_email = ChangeUserEmail(username, url)
    event["response"]["emailSubject"] = change_email.subject()
    event["response"]["emailMessage"] = change_email.render()
    return event


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    client_meta_data = event["request"]["clientMetadata"]
    portal_type = client_meta_data.get("portal")
    s3_config = get_s3_config(bucket_name, file_name, s3_client)
    url = s3_config[environment][portal_type]
    if event["triggerSource"] == "CustomMessage_AdminCreateUser":
        customized_event = get_welcome_email_template(event, url)
    elif event["triggerSource"] == "CustomMessage_ForgotPassword":
        customized_event = get_forgot_email_template(event, url)
    elif event["triggerSource"] == "CustomMessage_UpdateUserAttribute":
        customized_event = send_code_verify_email(event, url)
    return customized_event
