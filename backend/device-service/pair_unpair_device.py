import json
import logging
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from shared import get_db_connect, get_headers, get_phi_data, read_as_dict
from sqls.device import (
    GET_DEVICE_DETAILS,
    GET_PATIENT_DETAILS,
    INSERT_DEVICE_PAIRING,
    UPDATE_DEVICE_PAIRING,
)

dynamo_db = boto3.resource("dynamodb", region_name="us-east-1")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_patient_details_with_device(cnx, patient_internal_id):
    """
    Get Patient and paired device details for the selected patient
    """
    params = {"id": patient_internal_id}
    patient_details = read_as_dict(cnx, GET_PATIENT_DETAILS, params, fetchone=True)
    device_details = read_as_dict(cnx, GET_DEVICE_DETAILS, params, fetchone=True)
    if device_details:
        patient_details.update(device_details)
    else:
        patient_details.update({"device_pairing": None, "start_date": None})
    phi_data = get_phi_data(patient_details["external_id"], dynamo_db)
    patient_details.update(
        {
            "name": phi_data.get("first_name") + " " + phi_data.get("last_name"),
            "first_name": phi_data.get("first_name") if phi_data else "",
            "last_name": phi_data.get("last_name") if phi_data else "",
        }
    )
    return patient_details


def pair_device(cnx, imei, patient_internal_id, start_date):
    """
    Pair a Device
    """
    params = {
        "patient_internal_id": patient_internal_id,
        "imei": imei,
        "start_date": start_date,
        "active": "Y",
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_DEVICE_PAIRING, params)
            cnx.commit()
        logger.info(
            "Successfully assigned device ::%s to patient ::%s",
            imei,
            patient_internal_id,
        )
        patient_details = get_patient_details_with_device(cnx, patient_internal_id)
        return HTTPStatus.OK, patient_details
    except pymysql.MySQLError as err:
        logger.error(err)
    return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"


def unpair_device(cnx, patient_internal_id, end_date):
    """
    Unpair A Device
    """
    try:
        with cnx.cursor() as cursor:
            cursor.execute(
                UPDATE_DEVICE_PAIRING,
                {"end_date": end_date, "patient_internal_id": patient_internal_id},
            )
            cnx.commit()
            patient_details = get_patient_details_with_device(cnx, patient_internal_id)
        return HTTPStatus.OK, patient_details
    except pymysql.MySQLError as err:
        logger.error(err)
    return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"


def lambda_handler(event, context):
    """
    Handler Function
    """
    patient_internal_id = event["pathParameters"].get("patient_internal_id")
    form_data = json.loads(event["body"])
    if "pair_device" in event["path"].split("/"):
        imei = form_data["imei"]
        start_date = form_data["start_date"]
        start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
        status_code, result = pair_device(
            connection, imei, patient_internal_id, start_date
        )
    else:
        end_date = form_data["date_time"]
        end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
        status_code, result = unpair_device(connection, patient_internal_id, end_date)
    return {
        "statusCode": status_code.value,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
