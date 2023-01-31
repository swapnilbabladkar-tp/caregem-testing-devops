import json
import logging

from custom_exception import GeneralException
from shared import get_db_connect, get_headers, read_as_dict

logger = logging.getLogger(__name__)

cnx = get_db_connect()


def get_performance_metrics(patient_id):
    """
    Returns performance metrics for the selected patient
    """
    try:
        query = """SELECT * FROM performance_metrics WHERE patient_id = %s """
        patient_dict_rows = read_as_dict(cnx, query, (patient_id))
        final_patient_alert_trend = []
        for row in patient_dict_rows:
            item = {}
            item["create_date"] = row.get("create_date").strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            item["id"] = row.get("id")
            item["most_recent_flag"] = row.get("most_recent_flag")
            item["patient_id"] = row.get("patient_id")
            item["performance_metrics"] = row.get("performance_metrics")
            final_patient_alert_trend.append(item)
        return final_patient_alert_trend
    except GeneralException as e:
        logger.exception(e)


def lambda_handler(event, context):
    """
    The api will handle getting performance metrics for a patient
    """
    patient_id = event["pathParameters"].get("patient_id")
    user_result = get_performance_metrics(patient_id)
    return {
        "statusCode": 200,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
