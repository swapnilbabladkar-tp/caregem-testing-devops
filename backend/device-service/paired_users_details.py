import json
import logging
from http import HTTPStatus

import boto3
from shared import get_db_connect, get_headers, get_phi_data, read_as_dict
from sqls.device import GET_DEVICE_DETAILS, GET_PAIRED_USERS, GET_PATIENT_DETAILS

dynamo_db = boto3.resource("dynamodb", region_name="us-east-1")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_paired_user(cnx, imei):
    """
    Get the paired User Details
    """
    paired_patient = read_as_dict(cnx, GET_PAIRED_USERS, {"imei": imei}, fetchone=True)
    if paired_patient:
        params = {"id": paired_patient["patient_internal_id"]}
        patient_details = read_as_dict(cnx, GET_PATIENT_DETAILS, params, fetchone=True)
        device_details = read_as_dict(cnx, GET_DEVICE_DETAILS, params, fetchone=True)
        if device_details:
            patient_details.update(device_details)
        else:
            patient_details.update({"device_pairing": None, "start_date": None})
        phi_data = get_phi_data(patient_details["external_id"], dynamo_db)
        patient_details["first_name"] = phi_data.get("first_name", "")
        patient_details["last_name"] = phi_data.get("last_name", "")
        patient_details.update(
            {
                "name": phi_data.get("first_name") + " " + phi_data.get("last_name"),
                "first_name": phi_data.get("first_name") if phi_data else "",
                "last_name": phi_data.get("last_name") if phi_data else "",
            }
        )
        return HTTPStatus.OK, patient_details
    return HTTPStatus.OK, None


def lambda_handler(event, context):
    """
    Handler Function.
    """
    # auth_user = event["requestContext"].get("authorizer")
    imei_id = event["pathParameters"].get("imei_id")
    status_code, result = get_paired_user(connection, imei_id)
    return {"statusCode": 200, "body": json.dumps(result), "headers": get_headers()}
