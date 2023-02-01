import json
import logging

import pymysql
from shared import get_db_connect, get_headers, read_as_dict
from sqls.diagnosis import (
    DELETE_DIAGNOSIS_QUERY,
    PATIENT_DIAGNOSIS_QUERY,
    SAVE_DIAGNOSIS_QUERY,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
connection = get_db_connect()


def get_patient_diagnosis(cnx, patient_id):
    """
    Get the Diagnosis
    """
    result_set = read_as_dict(cnx, PATIENT_DIAGNOSIS_QUERY, {"patient_id": patient_id})
    logging.info(result_set)
    return 200, result_set


def save_patient_diagnosis(cnx, patient_id, diagnosis_code):
    """
    Save the diagnosis
    """
    try:
        with cnx.cursor() as cursor:
            cursor.execute(
                SAVE_DIAGNOSIS_QUERY,
                ({"code": diagnosis_code, "patient_id": patient_id}),
            )
            cnx.commit()
        return 200, {"msg": "Update successful."}
    except pymysql.MySQLError as err:
        logger.error(err)
        return 500, err


def delete_diagnosis(cnx, patient_id, diagnosis_code_list):
    """
    Delete the diagnosis attached to patient
    """
    try:
        with cnx.cursor() as cursor:
            cursor.execute(
                DELETE_DIAGNOSIS_QUERY,
                {"patient_id": patient_id, "codes": tuple(diagnosis_code_list)},
            )
            cnx.commit()
        return 200, {"msg": "Deleted successfully"}
    except pymysql.MySQLError as err:
        logger.error(err)
        return 500, err


def lambda_handler(event, context):
    """
    The api will handle user update, delete, read operations.
    """
    # auth_user = get_logged_in_user(event["headers"]["Authorization"])
    patient_internal_id = event["pathParameters"].get("patient_internal_id")
    if event["httpMethod"] == "GET":
        status_code, result = get_patient_diagnosis(connection, patient_internal_id)
    elif event["httpMethod"] == "POST":
        form_data = json.loads(event["body"])
        diagnosis = form_data["diagnoses"]
        status_code, result = save_patient_diagnosis(
            connection, patient_internal_id, diagnosis
        )
    elif event["httpMethod"] == "DELETE":
        diagnosis = event["queryStringParameters"].get("diagnoses")
        diagnosis_list = diagnosis.split(",")
        status_code, result = delete_diagnosis(
            connection, patient_internal_id, diagnosis_list
        )
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
