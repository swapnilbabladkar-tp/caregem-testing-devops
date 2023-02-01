import logging
from http import HTTPStatus

from custom_exception import GeneralException
from shared import (
    find_user_by_external_id,
    get_db_connect,
    json_response,
    read_as_dict,
    check_user_access_for_patient_data,
)
from sqls.patient_queries import PATIENT_LAB_DATA

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_lab_data(cnx, patient_id):
    """
    Get the Patient Lab data
    """
    try:
        patient_dict_rows = read_as_dict(
            cnx, PATIENT_LAB_DATA, {"patient_id": patient_id}
        )
        final_patient_lab_data = []
        for row in patient_dict_rows:
            item = dict()
            item["date_tested"] = row.get("date_tested").strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            item["id"] = row.get("id")
            item["most_recent_flag"] = row.get("most_recent_flag")
            item["name"] = row.get("name")
            item["patient_id"] = row.get("patient_id")
            item["value"] = row.get("value")
            final_patient_lab_data.append(item)
        return 200, final_patient_lab_data
    except GeneralException as err:
        logger.exception(err)
        return 500, str(err)


def lambda_handler(event, context):
    """
    Handler function
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
        status_code, user_result = get_lab_data(connection, patient_id)
    else:
        status_code = HTTPStatus.BAD_REQUEST
        user_result = access_result
    return json_response(user_result, status_code)
