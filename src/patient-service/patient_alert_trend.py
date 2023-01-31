import logging

from custom_exception import GeneralException
from shared import get_db_connect, json_response, read_as_dict
from sqls.patient_queries import ALERT_TREND_QUERY

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_alert_trend(cnx, patient_id):
    """
    Get Alert Trend For patient
    """
    try:
        patient_dict_rows = read_as_dict(
            cnx, ALERT_TREND_QUERY, {"patient_id": patient_id}
        )
        final_patient_alert_trend = []
        for row in patient_dict_rows:
            item = dict()
            item["alert_trends"] = row.get("alert_trends")
            item["alert_trends_text"] = row.get("alert_trends_text")
            item["create_date"] = row.get("create_date").strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            item["id"] = row.get("id")
            item["most_recent_flag"] = row.get("most_recent_flag")
            item["patient_id"] = row.get("patient_id")
            final_patient_alert_trend.append(item)
        logger.info(
            "Completed Execution for patient Alert Trends for patient ID %s ",
            patient_id,
        )
        return 200, final_patient_alert_trend
    except GeneralException as err:
        logger.error(err, exc_info=True)
        return 500, str(err)


def lambda_handler(event, context):
    """
    Handler Function
    """
    patient_id = event["pathParameters"].get("patient_id")
    status_code, user_result = get_alert_trend(connection, patient_id)
    return json_response(data=user_result, response_code=status_code)
