import logging
import os

import boto3
from botocore.exceptions import ClientError
from twilio_service import send_sms_to_number

logger = logging.getLogger(__name__)

sns = boto3.client("sns")


def get_join_video_call_sms_content(webapp_url: str):
    """
    Template function to return Video Call SMS content
    """
    return (
        f"Someone from your Care Team wants to connect with you now."
        f"\nTo join the meeting, please relogin the application or visit {webapp_url}"
    )


def get_device_reading_updated_sms_content(webapp_url: str):
    """
    Template function to return Device Reading SMS content
    """
    return f"Device readings for a patient has been uploaded\nTo view the readings please login to {webapp_url} on web or phone."


def get_patient_added_to_network_message_content(webapp_url: str):
    """
    Template function to return Network Addition SMS content
    """
    return f"A Patient has been added to your network on CAREGEM.\nTo view the patient please login to {webapp_url} on web or phone."


def get_phone_number_from_phi_data(phi_data):
    """
    Returns stripped phone number with country code based on input phi data
    """
    if phi_data:
        return (
            f"{phi_data.get('cell_country_code','')}{phi_data.get('cell','')}".replace(
                "-", ""
            )
        )
    return ""


def get_symptom_reported_message_content(level: int, org_name: str):
    """
    Template function to return Symptom Reported SMS content
    """
    if level == 2:
        return f"An ALERT SYMPTOM has been submitted by a patient in CAREGEM {org_name}. Please login to CAREGEM App to review."
    return f"A patient has submitted a survey in CAREGEM {org_name}. Please login to CAREGEM App to review."


def publish_text_message(phone_number: str, message: str):
    """
    Publishes a text message directly to a phone number without need for a
    subscription.

    :param phone_number: The phone number that receives the message. This must be
                         in E.164 format. For example, a United States phone
                         number might be +12065550101.
    :param message: The message to send.
    :return: The ID of the message in case SNS is used. Twilio returns None.
    """
    use_twilio = os.getenv("USE_TWILIO", "")
    use_twilio = True if use_twilio.lower() in ["true", "yes", "y", 1] else False
    if use_twilio:
        send_sms_to_number(phone_number, message)
        return
    try:
        response = sns.publish(PhoneNumber=str(phone_number), Message=str(message))
        message_id = response["MessageId"]
        logger.info("Published message to %s.", phone_number)
    except ClientError:
        logger.exception("Couldn't publish message to %s.", phone_number)
        raise
    else:
        return message_id
