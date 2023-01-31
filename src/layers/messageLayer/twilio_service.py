import logging
import os

from custom_exception import GeneralException
from dotenv import load_dotenv
from shared import (
    find_user_by_internal_id,
    get_db_connect,
    get_phi_data,
    get_secret_manager,
)
from twilio.rest import Client

load_dotenv()

sms_enabled = os.getenv("SMS_ENABLED", "")
sms_secret_id = os.getenv("ENCRYPTION_KEY_SECRET_ID", "")

sms_cred = get_secret_manager(sms_secret_id)
account_sid = sms_cred["sms_account_id"]
auth_token = sms_cred["auth_token"]
sms_from = sms_cred["sms_from"]


def _get_user_to_send_sms(cnx, receiver_id):
    """
    Returns User data required for sending sms for the input user internal id
    """
    try:
        receiver = find_user_by_internal_id(cnx, receiver_id)
        external_id = receiver["external_id"]
        profile_data = get_phi_data(external_id)
        user_sms_data = dict()
        user_sms_data["role"] = profile_data.get("role", "")
        user_sms_data["name"] = (
            profile_data.get("first_name") + " " + profile_data.get("last_name")
        )
        user_sms_data["cell"] = profile_data.get("cell", "")
        return user_sms_data
    except GeneralException as ex:
        logging.exception(ex)


def send_sms(receiver_id, sms_content, cnx=None):
    """
    This Function:
    1. Gets User data to send the message to based on receiver internal id
    2. Creates instance of twilio client using account id and auth token
    3. Sends SMS using messages.create method from twilio to user's cell number
    """
    if sms_enabled and sms_enabled.lower() == "true":
        try:
            if not cnx:
                cnx = get_db_connect()
            logging.info("Sending an SMS to the receiver")

            client = Client(account_sid, auth_token)
            user_sms_data = _get_user_to_send_sms(cnx, receiver_id)
            sms_to = (
                user_sms_data["cell"].replace("-", "").replace("(", "").replace(")", "")
            )
            # It is supposed to be "CAREGEM", but Twilio does not allow alphanumeric senders in USA.
            # sms_from = "+17085723344"
            client.messages.create(to=sms_to, from_=sms_from, body=sms_content)
        except GeneralException as e:
            logging.exception(e)


def send_sms_to_number(phone_number, sms_content):
    """
    This function :
    1. Creates instance of twilio client using account id and auth token
    2. Sends SMS using messages.create method from twilio to input phone number
    """
    if sms_enabled and sms_enabled.lower() == "true":
        try:
            logging.info("Sending an SMS to the receiver")
            client = Client(account_sid, auth_token)
            sms_to = phone_number.replace("-", "").replace("(", "").replace(")", "")
            # It is supposed to be "CAREGEM", but Twilio does not allow alphanumeric senders in USA.
            # sms_from = "+17085723344"
            client.messages.create(to=sms_to, from_=sms_from, body=sms_content)
        except GeneralException as e:
            logging.exception(e)
