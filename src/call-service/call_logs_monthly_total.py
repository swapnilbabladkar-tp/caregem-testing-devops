import json
import logging

from shared import (
    get_db_connect,
    get_headers,
    get_user_org_ids,
    read_as_dict,
    read_query,
)
from sqls.call import (
    CALL_LOGS_MONTHLY_TOTAL,
    CALL_LOGS_MONTHLY_TOTAL_RM_PRV,
    REMOTE_MONITORING_PROVIDER,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_common_org_id(cnx, patient_id, provider_id):
    """
    Get the common org id.
    :params patient_id, provider_id, cnx obj
    :Return common org_ids
    """
    pat_orgs = get_user_org_ids(cnx, "patient", internal_id=patient_id)
    prv_orgs = get_user_org_ids(cnx, "providers", internal_id=provider_id)
    common_org = set(pat_orgs).intersection(set(prv_orgs))
    if common_org:
        return list(common_org)
    return None


def get_call_logs_monthly_total(cnx, patient_id, provider_id, year, month):
    """
    Get the call logs monthly Total.
    :params patient_id, provider_id, year, month
    :Return call logs monthly total
    """
    rm_enabled = read_query(
        cnx, REMOTE_MONITORING_PROVIDER, {"provider_id": provider_id}
    )
    if rm_enabled:
        org_id = get_common_org_id(cnx, patient_id, provider_id)
        if not org_id:
            logger.info("no common org found")
            return 0
        params = {
            "org_id": org_id[0],
            "patient_id": patient_id,
            "month": month,
            "year": year,
            "status": tuple(["COMPLETED", "DRAFT"]),
        }
        result = read_as_dict(cnx, CALL_LOGS_MONTHLY_TOTAL_RM_PRV, params)
    else:
        result = read_as_dict(cnx, CALL_LOGS_MONTHLY_TOTAL, (patient_id, month, year))
    return int(result[0]["total"]) if result[0]["total"] else 0


def lambda_handler(event, context):
    """
    Handler Function
    """
    patient_id = event["pathParameters"].get("patient_id")
    provider_id = event["pathParameters"].get("provider_id")
    year = event["pathParameters"].get("year")
    month = event["pathParameters"].get("month")

    previous_month = int(month) - 1
    previous_year = int(year)

    if previous_month == 0:
        previous_month = 12
        previous_year = previous_year - 1

    result = {
        "currentMonthTotal": str(
            get_call_logs_monthly_total(
                connection, patient_id, provider_id, year, month
            )
        ),
        "priorMonthTotal": str(
            get_call_logs_monthly_total(
                connection, patient_id, provider_id, previous_year, previous_month
            )
        ),
    }

    return {"statusCode": 200, "body": json.dumps(result), "headers": get_headers()}
