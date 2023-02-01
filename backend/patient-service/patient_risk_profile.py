import json
import logging
from http import HTTPStatus

from custom_exception import GeneralException
from shared import (
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    read_as_dict,
    check_user_access_for_patient_data,
)
from sqls.patient_queries import PATIENT_RISK_PROFILE

logger = logging.getLogger(__name__)

connection = get_db_connect()


def get_risk_profile(cnx, patient_id):
    """
    Returns Risk Profile data for a selected patient
    """
    try:
        patient_dict_rows = read_as_dict(
            cnx, PATIENT_RISK_PROFILE, {"patient_id": patient_id}
        )
        final_patient_risk_profile = []
        for row in patient_dict_rows:
            item = dict()
            item["create_date"] = row.get("create_date").strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            item["id"] = row.get("id")
            item["most_recent_flag"] = row.get("most_recent_flag")
            item["patient_id"] = row.get("patient_id")
            item["risk_profile"] = row.get("risk_profile")
            final_patient_risk_profile.append(item)
        return 200, final_patient_risk_profile
    except GeneralException as exp:
        logger.exception(exp)
        return 500, exp


def lambda_handler(event, context):
    """
    The api will handle getting risk profile for a patient
    """
    auth_user = event["requestContext"].get("authorizer")
    external_id = auth_user["userSub"]
    role = auth_user["userRole"]
    user_data = find_user_by_external_id(connection, external_id, role)
    patient_id = event["pathParameters"].get("patient_id")
    is_allowed, access_result = check_user_access_for_patient_data(
        cnx=connection,
        role=role,
        user_data=user_data,
        patient_internal_id=patient_id,
    )
    if is_allowed and access_result and access_result["message"] == "Success":
        status_code, user_result = get_risk_profile(connection, patient_id)
    else:
        status_code = HTTPStatus.BAD_REQUEST
        user_result = access_result
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
