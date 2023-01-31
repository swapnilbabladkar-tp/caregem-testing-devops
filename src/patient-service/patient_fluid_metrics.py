import json
import logging

import pymysql
from shared import get_analytics_connect, get_headers, read_as_dict
from sqls.fluid_metric import FLUID_METRIC_QUERY

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_analytics_connect()


def get_patient_fluid_metrics(cnx, patient_internal_id, status=None):
    """
    Get Fluid Metrics Data for the Patient
    Returns True or False if status param has a value
    """
    try:
        result = read_as_dict(cnx, FLUID_METRIC_QUERY, patient_internal_id)
        if status:
            is_available = len(result) > 0
            return {"result": "True" if is_available else "False"}
        logger.info(
            "Completed Execution of Fluid Metric for patient id %s", patient_internal_id
        )
        return 200, result if result else []
    except pymysql.MySQLError as err:
        logger.error(err)
        return 500, err


def lambda_handler(event, context):
    """
    The api will tell if patient has fluid metrics or not
    """
    patient_internal_id = event["pathParameters"].get("patient_internal_id")
    if "hasfluidmetrics" in event["path"].split("/"):
        status_code, user_result = get_patient_fluid_metrics(
            connection, patient_internal_id, True
        )
    elif "fluid_metric" in event["path"].split("/"):
        status_code, user_result = get_patient_fluid_metrics(
            connection, patient_internal_id, None
        )
    return {
        "statusCode": 200,
        "body": json.dumps(user_result, default=str),
        "headers": get_headers(),
    }
