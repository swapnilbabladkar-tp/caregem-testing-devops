import logging

import boto3
from custom_exception import GeneralException
from shared import (
    get_analytics_connect,
    get_db_connect,
    get_phi_data,
    json_response,
    read_as_dict,
)
from sqls.patient_queries import PATIENT_DETAILS

dynamodb = boto3.resource("dynamodb")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()
aconnection = get_analytics_connect()


def get_patient_chart_status(cnx, acnx, patient_internal_id, symptom_type):
    """
    Patient Chart Status
    """
    try:
        patient_info = read_as_dict(
            cnx, PATIENT_DETAILS, {"patient_id": patient_internal_id}
        )[0]
        if patient_info is None:
            return 200, []
        patient_phi = get_phi_data(patient_info["external_id"], dynamodb)
        patient_info.update(patient_phi)
        name = f"{patient_info['last_name']}, {patient_info['first_name']}"
        view_name = "analytics_" + symptom_type
        username = patient_info["email"]
        sql = (
            "SELECT *, '"
            + name
            + "' as name, tstamp AS submission_date FROM "
            + view_name
            + " WHERE email_id = '"
            + username
            + "' ORDER  BY STR_TO_DATE(tstamp, '%m/%d/%Y') "
        )

        patient_dict_rows = read_as_dict(acnx, sql)

        is_available = len(patient_dict_rows) > 0
        return {"result": "True" if is_available else "False"}

    except GeneralException as e:
        logger.exception(e)


def lambda_handler(event, context):
    """
    Handler Function
    """
    patient_internal_id = event["pathParameters"].get("patient_internal_id")
    symptom_type = event["pathParameters"].get("symptom_type")
    status_code, user_result = get_patient_chart_status(
        connection, aconnection, patient_internal_id, symptom_type
    )
    return json_response(data=user_result, response_code=status_code)
