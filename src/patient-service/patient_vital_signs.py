import json
import logging
from datetime import timedelta
from http import HTTPStatus

from custom_exception import GeneralException
from shared import (
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    read_as_dict,
    check_user_access_for_patient_data,
)
from sqls.vital import BP_HR_QUERY, RM_VALES_QUERY, WEIGHT_QUERY

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


connection = get_db_connect()

bp_posture_mapper = {
    "Sit": "Sitting",
    "Stand": "Standing",
    "Sitting": "Sitting",
    "Standing": "Standing",
    "Lying": "Lying",
}


def get_vital_signs(cnx, patient_id, duration):
    """
    Get Vitals Data manually reported for the patient
    Vitals data contains BP, Heart Rate and Weight Data
    """
    try:
        bp_report = read_as_dict(cnx, BP_HR_QUERY, (patient_id, duration))
        wt_report = read_as_dict(cnx, WEIGHT_QUERY, (patient_id, duration))
        final_list = []
        bp_report_list = []
        wt_final_list = []
        for bp in bp_report:
            item = dict()
            item["key_id"] = bp["id"]
            item["am_systolic_top"] = bp_am_top = bp.get("am_systolic_top", "")
            item["am_diastolic_bottom"] = bp_am_bot = bp.get("am_diastolic_bottom", "")
            item["pm_systolic_top"] = bp_pm_top = bp.get("pm_systolic_top", "")
            item["pm_diastolic_bottom"] = bp_pm_bot = bp.get("pm_diastolic_bottom", "")
            item["am_bp"] = (
                ""
                if bp_am_top in ("", None) or bp_am_bot in ("", None)
                else str(bp_am_top) + "/" + str(bp_am_bot)
            )
            item["pm_bp"] = (
                ""
                if bp_pm_top in ("", None) or bp_pm_bot in ("", None)
                else str(bp_pm_top) + "/" + str(bp_pm_bot)
            )
            item["bp_report"] = bp.get("bp_report", "")
            item["bp_taken_when"] = bp.get("bp_taken_when", "")
            item["bp_taken_time"] = bp.get("bp_taken_time", "")
            item["bp_taken_date"] = (
                bp["bp_taken_date"].strftime("%m/%d/%Y %H:%M:%S")
                if bp.get("bp_taken_date")
                else ""
            )
            bp_posture = bp.get("bp_posture", "")
            item["pos"] = bp_posture_mapper.get(bp_posture, "")
            item["reported_by"] = bp.get("submitted_by", "")
            item["reported_on"] = bp["tstamp"].strftime("%m/%d/%Y %H:%M:%S")
            item["symptoms"] = bp.get("bp_comments", "")
            if not bp.get("bp_taken_date"):
                item["bp_taken_on"] = bp["tstamp"].strftime("%m/%d/%Y %H:%M:%S")
            else:
                item["bp_taken_on"] = bp["bp_taken_date"].strftime("%m/%d/%Y %H:%M:%S")
            item["h_pulse"] = bp.get("heart_rate", "")
            item["hr_report"] = bp.get("hr_report", "")
            item["hr_taken_when"] = bp.get("hr_taken_when", "")
            item["hr_taken_date"] = (
                bp["hr_taken_date"].strftime("%m/%d/%Y %H:%M:%S")
                if bp.get("hr_taken_date")
                else ""
            )
            bp_report_list.append(item)
        for wt in wt_report:
            item = dict()
            item["ch_kg"] = wt.get("weight_kilograms", "")
            item["ch_lb"] = wt.get("weight_pounds", "")
            item["reported_by"] = wt.get("submitted_by", "")
            item["reported_on"] = wt["tstamp"].strftime("%m/%d/%Y %H:%M:%S")
            if not wt.get("weight_taken_date", ""):
                item["weight_taken_on"] = wt["tstamp"].strftime("%m/%d/%Y %H:%M:%S")
            else:
                item["weight_taken_on"] = wt["weight_taken_date"].strftime(
                    "%m/%d/%Y %H:%M:%S"
                )
            wt_final_list.append(item)
        final_list.extend(bp_report_list)
        final_list.extend(wt_final_list)
        logger.info("Completed Execution for Patient Vital Signs")
        return 200, final_list
    except GeneralException as err:
        logger.error(err, exc_info=True)
        return 500, err


def convert_regular_to_string(reg):
    """
    Converts 0/1 value in input to Regular/Irregular for BP data
    """
    if reg == "0":
        return "Regular"
    return "Irregular"


def get_rm_values(cnx, patient_internal_id, duration):
    """
    Get BP Device Readings reported from the remote device linked to the patient
    """
    try:
        patient_dict_rows = read_as_dict(
            cnx, RM_VALES_QUERY, (patient_internal_id, duration)
        )

        final_rm_values = []

        for row in patient_dict_rows:
            bp_top = int(round(int(row.get("systolic", "")) * 0.0075006))
            bp_bot = int(round(int(row.get("diastolic", "")) * 0.0075006))
            bp_join = str(bp_top) + "/" + str(bp_bot)
            pulse = row.get("pulse", "")
            regular = convert_regular_to_string(row.get("irregular", ""))
            bpt = row.get("timestamp", "")
            key_id = row.get("id", "")
            final_rm_values.append(
                {
                    "bp_taken_on": bpt.strftime("%m-%d-%Y %I:%M %p"),
                    "am_bp": bp_join
                    if (bpt - timedelta(hours=5)).strftime("%p") == "AM"
                    else "",
                    "pm_bp": bp_join
                    if (bpt - timedelta(hours=5)).strftime("%p") == "PM"
                    else "",
                    "h_pulse": pulse,
                    "reg": regular,
                    "key_id": key_id,
                }
            )
        logger.info("Completed Execution for Patient RM Values")
        return 200, final_rm_values
    except GeneralException as err:
        logger.error(err)
        return 500, err


def lambda_handler(event, context):
    """
    The api will handle getting vital signs for a patient
    """
    auth_user = event["requestContext"].get("authorizer")
    external_id = auth_user["userSub"]
    role = auth_user["userRole"]
    user_data = find_user_by_external_id(connection, external_id, role)
    patient_id = event["pathParameters"].get("patient_id")
    v_type = event["queryStringParameters"].get("type")
    duration = event["queryStringParameters"].get("duration")
    is_allowed, access_result = check_user_access_for_patient_data(
        cnx=connection,
        role=role,
        user_data=user_data,
        patient_internal_id=patient_id,
    )
    if is_allowed and access_result and access_result["message"] == "Success":
        if v_type == "Manual":
            status_code, user_result = get_vital_signs(connection, patient_id, duration)
        elif v_type == "Remote":
            status_code, user_result = get_rm_values(connection, patient_id, duration)
        else:
            status_code, user_result = get_vital_signs(connection, patient_id, duration)
            status_code, result = get_rm_values(connection, patient_id, duration)
            user_result.extend(result)
    else:
        status_code = HTTPStatus.BAD_REQUEST
        user_result = access_result
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
