import base64
import json
import logging
import os
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from custom_exception import GeneralException
from notification import insert_to_remote_vital_notification_table
from shared import (
    encrypt,
    get_db_connect,
    get_headers,
    get_phi_data_list,
    get_secret_manager,
    read_as_dict,
)
from sqls.device import GET_NETWORK_PROVIDERS, INSERT_DEVICE_READING

api_secret_id = os.getenv("API_KEYS")
environment = os.getenv("ENVIRONMENT")
bucket_name = os.getenv("BUCKET_NAME")
file_name = os.getenv("S3_FILE_NAME")
aws_region = os.getenv("AWSREGION")
s3_client = boto3.client("s3", region_name=aws_region)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")
connection = get_db_connect()


DEFAULT_NOTIFICATION_STATUS = 1
DEFAULT_NOTIFICATION_LEVEL = 1


def post_device_reading(cnx, d_type, record_dict):
    """
    Insert Device Reading into device_reading Table
    """
    device_reading_id = None
    if d_type != "BT105":
        return HTTPStatus.BAD_REQUEST, "Device Type is Not supported", device_reading_id
    if not record_dict.get("values"):
        logger.info("Device Ping")
        return (
            HTTPStatus.CONTINUE,
            f"Device Ping from device imei {record_dict['imei']}",
            device_reading_id,
        )
    time_utc = datetime.utcfromtimestamp(float(record_dict["ts"]) / 1000.0)
    params = {
        "imei": record_dict["imei"],
        "timestamp": time_utc,
        "battery_voltage": record_dict["batteryVoltage"],
        "signalStrength": record_dict["signalStrength"],
        "systolic": record_dict["values"]["systolic"],
        "diastolic": record_dict["values"]["diastolic"],
        "pulse": record_dict["values"]["pulse"],
        "irregular": record_dict["values"]["irregular"],
        "unit": record_dict["values"]["unit"],
        "raw": json.dumps(record_dict),
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_DEVICE_READING, params)
            device_reading_id = cursor.lastrowid
            cnx.commit()
        return HTTPStatus.OK, "Device Details Inserted Successfully ", device_reading_id
    except pymysql.MySQLError as err:
        logger.error(err)
    except KeyError as kerr:
        logger.error(kerr)
    return (
        HTTPStatus.INTERNAL_SERVER_ERROR,
        f"Error While updating device Reading for {record_dict['imei']}.",
        device_reading_id,
    )


def get_name_from_phi_data(phi_data):
    """
    Construct name string from input phi_data dict
    """
    return f"{phi_data['first_name']}, {phi_data['last_name']}"


def get_notification_details(phi_data_dict, patient_external_id):
    """
    Construct notification_details string for selected patient
    """
    name = get_name_from_phi_data(phi_data_dict[patient_external_id])
    return f"A Remote Vital device reading has been reported for {name}"


def insert_notification_for_network_providers(
    network_prv_dict: list,
    patient_internal_id: int,
    notification_details: str,
    device_reading_id: int,
):
    """
    Inserts remote vital notification for all network users
    """
    current_time = datetime.utcnow()
    for user in network_prv_dict:
        user_internal_id = user["internal_id"]
        insert_to_remote_vital_notification_table(
            remote_vital_id=device_reading_id,
            patient_internal_id=patient_internal_id,
            notifier_internal_id=user_internal_id,
            level=DEFAULT_NOTIFICATION_LEVEL,
            notification_details=encrypt(notification_details),
            created_on=current_time,
            updated_on=current_time,
            created_by=patient_internal_id,
            updated_by=patient_internal_id,
            notification_status=DEFAULT_NOTIFICATION_STATUS,
        )


def notify_network_providers(cnx, imei: str, device_reading_id):
    """
    This Function:
    1. Gets all network users linked to the patient
       with whom the device is paired
    2. Inserts Remote Vital Notification for network users
    3. Sends SMS to network users with alert_receiver enabled
    """
    if not imei:
        return HTTPStatus.BAD_REQUEST, "Invalid Imei value"
    try:
        network_prv_dict = read_as_dict(cnx, GET_NETWORK_PROVIDERS, {"imei": str(imei)})
        network_external_ids = []
        if network_prv_dict:
            for prv in network_prv_dict:
                if prv["user_alert_receiver"] == 1:
                    network_external_ids.append(prv["external_id"])
        if (
            isinstance(network_prv_dict, list)
            and len((network_prv_dict)) > 0
            and device_reading_id
        ):
            patient_internal_id: int = network_prv_dict[0].get("patient_internal_id")
            patient_external_id: int = network_prv_dict[0].get("patient_external_id")
            phi_external_ids = network_external_ids + [patient_external_id]
            phi_data_dict = get_phi_data_list(phi_external_ids, dynamodb)
            notification_details = get_notification_details(
                phi_data_dict, patient_external_id
            )
            insert_notification_for_network_providers(
                network_prv_dict,
                patient_internal_id,
                notification_details,
                device_reading_id,
            )
            return HTTPStatus.OK, "Successfully notified network providers"
    except pymysql.MySQLError as err:
        logger.error(err)
    except KeyError as kerr:
        logger.error(kerr)
    except GeneralException as err:
        logger.error(err)
    return HTTPStatus.INTERNAL_SERVER_ERROR, "Failed to notify network providers"


def lambda_handler(event, context):
    """
    Handler function for Device
    """
    logger.info("device_reading called")
    headers = event["headers"]
    if "Authorization" not in headers:
        logger.error("Authorization missing")
        return {"result": "Authorization Failed"}
    authorization = event["headers"]["Authorization"]
    authorization = authorization.split(" ")[1]
    basic_auth = base64.b64decode(authorization).decode()
    auth = basic_auth.split(":")
    username, password = auth[0], auth[1]
    device_secret = get_secret_manager(api_secret_id)
    secret = device_secret["device_password"] if device_secret else ""
    secret = secret + "_" + username
    model_type = event["pathParameters"].get("model_type")
    if secret != password + "_" + model_type:
        logger.info("Authorization Invalid")
        return {
            "statusCode": HTTPStatus.BAD_REQUEST,
            "body": json.dumps({"result": "Authorization Invalid"}),
            "headers": get_headers(),
        }
    form_data = json.loads(event["body"])
    status_code, result, device_reading_id = post_device_reading(
        connection, model_type, form_data
    )
    if status_code == HTTPStatus.OK:
        notification_status_code, notification_result = notify_network_providers(
            connection, form_data.get("imei", ""), device_reading_id
        )
        logger.info(str(notification_status_code) + notification_result)
        result = result + notification_result
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
