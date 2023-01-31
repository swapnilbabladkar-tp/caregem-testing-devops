import json
import logging

from custom_exception import GeneralException
from shared import get_db_connect, get_headers, read_as_dict
from sqls.patient_queries import PATIENT_UTILIZATION_QUERY

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_utilization(cnx, patient_id):
    """
    Get the patient utilization
    """
    try:
        params = {"patient_id": patient_id}
        patient_dict_rows = read_as_dict(cnx, PATIENT_UTILIZATION_QUERY, params)
        final_patient_alert_trend = []
        for row in patient_dict_rows:
            item = dict()
            item["create_date"] = row.get("create_date").strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            item["id"] = row.get("id")
            item["most_recent_flag"] = row.get("most_recent_flag")
            item["patient_id"] = row.get("patient_id")
            item["utilization"] = row.get("utilization")
            final_patient_alert_trend.append(item)
        logger.info("Completed Execution for Patient utilization")
        return 200, final_patient_alert_trend
    except GeneralException as e:
        500, logger.exception(e)


def lambda_handler(event, context):
    """
    The api will handle getting utilization for a patient
    """
    patient_id = event["pathParameters"].get("patient_id")
    status_code, user_result = get_utilization(connection, patient_id)
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
