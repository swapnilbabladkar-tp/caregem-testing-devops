import json
import logging
import traceback
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from custom_exception import GeneralException
from email_template import SurveyCompletionEmail, send_mail_to_user
from notification import insert_to_symptom_notifications_table
from shared import (
    encrypt,
    find_user_by_external_id,
    find_user_by_internal_id,
    get_analytics_connect,
    get_db_connect,
    get_headers,
    get_phi_data_from_internal_id,
    get_phi_data_list,
    read_as_dict,
)
from sms_util import (
    get_phone_number_from_phi_data,
    get_symptom_reported_message_content,
    publish_text_message,
)
from sqls.misc import (
    GET_DESC_ORDER_NORMALIZED_CHESTPAIN_FOR_PATIENT,
    GET_DESC_ORDER_NORMALIZED_FEVER_FOR_PATIENT,
    GET_DESC_ORDER_NORMALIZED_SHORTNESS_OF_BREATH_FOR_PATIENT,
    GET_DESC_ORDER_NORMALIZED_ULCERS_FOR_PATIENT,
    GET_NETWORK_PROVIDERS,
    GET_NORMALIZED_ACHES_PAIN,
    GET_NORMALIZED_APPETITE_IMPAIRMENT,
    GET_NORMALIZED_CHESTPAIN,
    GET_NORMALIZED_FALLS,
    GET_NORMALIZED_FATIGUE,
    GET_NORMALIZED_FEVER,
    GET_NORMALIZED_LEG_SWELLING,
    GET_NORMALIZED_LIGHTHEADEDNESS,
    GET_NORMALIZED_NAUSEA,
    GET_NORMALIZED_SHORTNESS_OF_BREATH,
    GET_NORMALIZED_ULCERS,
    GET_ORG_NAME_FOR_PATIENT,
    INSERT_SURVEY_APPETITE,
    INSERT_SURVEY_BREATH,
    INSERT_SURVEY_CHESTPAIN,
    INSERT_SURVEY_DIALYSIS,
    INSERT_SURVEY_FALLS,
    INSERT_SURVEY_FATIGUE,
    INSERT_SURVEY_FEVER,
    INSERT_SURVEY_LIGHTHEADEDNESS,
    INSERT_SURVEY_MOOD,
    INSERT_SURVEY_NAUSEA,
    INSERT_SURVEY_PAIN,
    INSERT_SURVEY_SWELLING,
    INSERT_SURVEY_ULCERS,
    INSERT_SURVEY_URINARY,
    INSERT_SURVEY_VITALS,
    INSERT_SURVEY_WEIGHTCHANGE,
    INSERT_SYMPTOMS_TABLE,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")

mlprep_cnx = get_analytics_connect()
carex_cnx = get_db_connect()

SYMPTOM_MEDICAL_DATA_TYPE = "symptoms"

DEFAULT_NOTIFICATION_STATUS = 1


def get_string_from_input(input):
    """
    This Function:
    1. Returns string as it is if input is string
    2. Converts and returns input as string if input is int
    3. Joins and returns data as comma seperated string when input is tuple or list
    """
    if isinstance(input, str):
        return input
    if isinstance(input, int):
        return str(input)
    if isinstance(input, tuple) or isinstance(input, list):
        return ", ".join(input)
    return ""  # return empty string if the input value isnt valid to be parsed into a string


def get_symptom_notification_details(
    symptom_name,
    submitter_internal_id,
    patient_internal_id,
    patient_name,
    provider_name=None,
    provider_degree=None,
):
    """
    Generated notfication detail from input symptom data
    """
    if submitter_internal_id == patient_internal_id:
        return f"{patient_name} has submitted new {symptom_name} symptom"
    if provider_degree:
        return f"{patient_name} has new {symptom_name} symptom submitted by {provider_name},{provider_degree}"
    return f"{patient_name} has new {symptom_name} symptom submitted by {provider_name}"


def get_datetime_value_from_string(timestamp, customFormat=None):
    """
    Returns input date string as datetime data
    Returns object as it is if the data is already datetime
    """
    if isinstance(timestamp, datetime):
        return timestamp
    if isinstance(customFormat, str):
        return datetime.strptime(timestamp, customFormat)
    return datetime.strptime(timestamp, "%m/%d/%Y %H:%M:%S")


def insert_notification_for_network_providers(
    medical_data_type,
    medical_data_id,
    patient_internal_id,
    level,
    notification_details,
    created_on,
    created_by,
    notification_status,
):
    """
    This Function:
    1. Gets list of all Network Users for patient
    2. Gets Patient data
    3. Inserts Symtpom Notification for all network users regarding inserted symptom
    4. Sends SMS to providers who have alert_receiver turned on for the patient
    """
    network_providers = read_as_dict(
        carex_cnx, GET_NETWORK_PROVIDERS, {"patient_internal_id": patient_internal_id}
    )
    patient_org_data = read_as_dict(
        carex_cnx,
        GET_ORG_NAME_FOR_PATIENT,
        {"patient_internal_id": patient_internal_id},
        fetchone=True,
    )
    patient_org_name = (
        patient_org_data.get("org_name", "")
        if patient_org_data and isinstance(patient_org_data, dict)
        else ""
    )
    if network_providers:
        network_user_external_ids = []
        for user in network_providers:
            if user["network_alert_receiver"] == 1:
                user_external_id = (
                    user["provider_external_id"] or user["caregiver_external_id"]
                )
                network_user_external_ids.append(user_external_id)

        phi_data_dict = get_phi_data_list(network_user_external_ids, dynamodb)
        for user in network_providers:
            user_internal_id = (
                user["provider_internal_id"] or user["caregiver_internal_id"]
            )
            user_external_id = (
                user["provider_external_id"] or user["caregiver_external_id"]
            )
            insert_to_symptom_notifications_table(
                medical_data_type,
                medical_data_id,
                patient_internal_id,
                level,
                notification_details,
                created_on,
                created_by,
                notification_status,
                user_internal_id,
            )
            if user["network_alert_receiver"] == 1:
                phone_number = get_phone_number_from_phi_data(
                    phi_data_dict[user_external_id]
                )
                symptom_notification = get_symptom_reported_message_content(
                    level, patient_org_name
                )
                if phone_number:
                    message_id = publish_text_message(
                        phone_number, symptom_notification
                    )
                    logger.info(f"Message sent with message ID : {message_id}")


def insert_symptom_notification(
    symptom_name,
    symptom_id,
    patient_internal_id,
    submitter_internal_id,
    submitted_by,
    flag_read,
    created_time,
):
    """
    This Function:
    1. Gets PHI data for patient
    2. Generates notification_detail based on symptom reported and reporter
    3. Sends Survey Completion email to patient
    4. Calls function to insert Notification for all network users
    """
    patient_phi_data = get_phi_data_from_internal_id(
        carex_cnx, dynamodb, patient_internal_id
    )
    if patient_internal_id != submitter_internal_id:
        submitter_user_data = find_user_by_internal_id(carex_cnx, submitter_internal_id)
        patient_name = (
            f"{patient_phi_data['first_name']} {patient_phi_data['last_name']}"
            if patient_phi_data
            else ""
        )
        provider_degree = (
            submitter_user_data["degree"]
            if submitter_user_data and "degree" in submitter_user_data
            else ""
        )
        notification_detail = get_symptom_notification_details(
            symptom_name,
            submitter_internal_id,
            patient_internal_id,
            patient_name,
            submitted_by,
            provider_degree,
        )
    else:
        notification_detail = get_symptom_notification_details(
            symptom_name,
            submitter_internal_id,
            patient_internal_id,
            submitted_by,
        )
    notification_detail = encrypt(notification_detail)
    survey_completion_email_content = SurveyCompletionEmail(
        patient_phi_data.get("first_name", "") if patient_phi_data else ""
    )
    email = patient_phi_data.get("email", "") if patient_phi_data else ""
    if email:
        send_mail_to_user([email], survey_completion_email_content)
    insert_notification_for_network_providers(
        SYMPTOM_MEDICAL_DATA_TYPE,
        symptom_id,
        patient_internal_id,
        flag_read,
        notification_detail,
        created_time,
        submitter_internal_id,
        DEFAULT_NOTIFICATION_STATUS,
    )


def calculate_alert_aches_pain(row):
    """
    Calculates Alert level for aches/pain symtpom based on input
    """
    level = int(row.get("level", "0"), base=10)
    frequency = row.get("frequency", "")
    update = 1

    if level >= 7:
        update = 2
    elif level >= 4 and (frequency in ["24c", "24d"]):
        update = 2

    return update


def calculate_alert_appetite_impairment(row):
    """
    Calculates Alert level for appetite impairment symtpom based on input
    """
    level = row.get("level", "")
    update = 1

    if level in ["18c", "18d"]:
        update = 2

    return update


def calculate_alert_chest_pain(row):
    """
    Calculates Alert level for chest pain symtpom based on input data
    and if shortness of breath has been reported in last 48 hours
    """
    recentpain = row.get("recentpain", "")
    restpain = row.get("restpain", "")
    level = row.get("level", "")
    _type = row.get("type", "")
    length = row.get("length", "")
    worse = row.get("worse", "")
    better = row.get("better", "")
    frequency = row.get("frequency", "")
    patient_id = row.get("internal_id", "")
    tstamp = row.get("tstamp", "")
    update = 1  # default return value
    other_row = None

    try:
        # connect to database here
        other_row = read_as_dict(
            mlprep_cnx,
            GET_DESC_ORDER_NORMALIZED_SHORTNESS_OF_BREATH_FOR_PATIENT,
            (patient_id),
            fetchone=True,
        )
    except GeneralException as e:
        logging.exception(e)
    recent_high_level_chest_pain = (
        (recentpain == "1a" and level in ["4", "5", "6"])
        or (
            recentpain in ["1b", "1c"]
            and level in ["4", "5", "6"]
            and length in ["5b", "5c", "5d"]
        )
        or (
            recentpain in ["1a", "1b"]
            and level in ["1", "2", "3"]
            and length in ["5b", "5c"]
            and frequency in ["8c", "8d"]
        )
        or (recentpain in ["1a", "1b"] and level in ["1", "2", "3"] and length == "5d")
    )
    worse_high_level_chest_pain = (
        worse == "Exertion"
        and _type in ["Heaviness", "Dull/Aching"]
        and length in ["5c", "5d"]
    ) or (
        worse == "Deep breathing/coughing"
        and _type == "Dull/Aching"
        and level in ["5", "6"]
    )
    if recent_high_level_chest_pain:
        update = 2
    elif restpain == "2a":
        update = 2
    elif level in ["7"]:
        update = 2
    elif worse_high_level_chest_pain:
        update = 2
    elif (
        worse == "Exertion"
        and _type in ["Heaviness", "Dull/Aching"]
        and recentpain in ["1a", "1b"]
    ) or (
        worse == "Deep breathing/coughing"
        and _type in ["Sharp/Stabbing", "Dull/Aching"]
    ):
        update = 2
    elif (
        better == "Nothing/unrelieved by rest or medicine"
        and length in ["5c", "5d"]
        and recentpain in ["1a", "1b"]
    ):
        update = 2
    elif other_row is not None and isinstance(other_row, dict):
        level2 = other_row.get("level", "")
        tstamp2 = other_row.get("tstamp", "")

        t1 = get_datetime_value_from_string(tstamp)
        t2 = get_datetime_value_from_string(tstamp2)
        difference = t1 - t2
        time_diff = difference.total_seconds() / 3600.0

        if frequency in ["8c", "8d"] and level2 == "10b" and (0 <= time_diff <= 48):
            update = 2

    return update


def calculate_alert_falls(row):
    """
    Calculates Alert level for falls symtpom based on input
    """
    falls = row.get("falls", "")
    update = 1

    if falls == "Yes":
        update = 2

    return update


def calculate_alert_fatigue(row):
    """
    Calculates Alert level for fatigue symtpom based on input
    """
    level = row.get("level", "")
    update = 1

    if level == "20d":
        update = 2

    return update


def calculate_alert_fever(row):
    """
    Calculates Alert level for fever symtpom based on input
    and if ulcer has been reported in last 48 hours
    """
    level = row.get("level", "")
    frequency = row.get("frequency", "")
    tstamp = row.get("tstamp", "")
    patient_id = row.get("internal_id", "")
    other_row = None
    update = 1

    try:
        other_row = read_as_dict(
            mlprep_cnx,
            GET_DESC_ORDER_NORMALIZED_ULCERS_FOR_PATIENT,
            (patient_id),
            fetchone=True,
        )
    except GeneralException as e:
        logging.exception(e)

    if (level in ["12c", "12d"]) or frequency == "13c":
        update = 2
    elif other_row is not None and isinstance(other_row, dict):

        ulcers = other_row.get("ulcers", "")
        tstamp2 = other_row.get("tstamp", tstamp)

        t1 = get_datetime_value_from_string(tstamp)
        t2 = get_datetime_value_from_string(tstamp2)
        difference = t1 - t2
        time_diff = difference.total_seconds() / 3600.0

        if ulcers == "Yes" and level == "12b" and (0 <= time_diff <= 48):
            update = 2

    return update


def calculate_alert_leg_swelling(row):
    """
    Calculates Alert level for log swelling symtpom based on input
    """
    level = row.get("level", "")
    update = 1

    if level in ["39b", "39c"]:
        update = 2

    return update


def calculate_alert_light_headedness(row):
    """
    Calculates Alert level for lightheadedness symtpom based on input
    """
    level = row.get("level", "")
    frequency = row.get("frequency", "")
    update = 1

    if (frequency in ["29d", "29e"]) or (
        level
        in [
            "Vision impairment/greying out",
            "Near passing out",
            "Loss of consciousness",
        ]
    ):
        update = 2

    return update


def calculate_alert_nausea(row):
    """
    Calculates Alert level for nausea symtpom based on input
    """
    level = row.get("level", "")
    frequency = row.get("frequency", "")
    update = 1

    if frequency == "15d":
        update = 2
    elif level == "16c":
        update = 2

    return update


def calculate_alert_shortness_of_breath(row):
    """
    Calculates Alert level for shortness of breath symtpom based on input
    and if chest pain has been reported in last 48 hours
    """
    patient_id = row.get("internal_id", "")
    other_row = None
    try:
        # connect to database here
        other_row = read_as_dict(
            mlprep_cnx,
            GET_DESC_ORDER_NORMALIZED_CHESTPAIN_FOR_PATIENT,
            (patient_id),
            fetchone=True,
        )
    except GeneralException as e:
        logging.exception(e)

    level = row.get("level", "")
    tstamp = row.get("tstamp", "")

    update = 1

    if level in ["10c", "10d"]:
        update = 2
    elif other_row is not None and isinstance(other_row, dict):
        frequency = other_row.get("frequency", "")
        tstamp2 = other_row.get("tstamp", tstamp)

        t1 = get_datetime_value_from_string(tstamp)
        t2 = get_datetime_value_from_string(tstamp2)
        difference = t1 - t2
        time_diff = difference.total_seconds() / 3600.0

        if level == "10b" and frequency in ["8d", "8e"] and (0 <= time_diff <= 48):
            update = 2

    return update


def calculate_alert_ulcers(row):
    """
    Calculates Alert level for ulcers symtpom based on input
    and if fever has been reported in last 48 hours
    """
    patient_id = row.get("internal_id", "")
    other_row = None

    try:
        other_row = read_as_dict(
            mlprep_cnx,
            GET_DESC_ORDER_NORMALIZED_FEVER_FOR_PATIENT,
            (patient_id),
            fetchone=True,
        )
    except GeneralException as e:
        logging.exception(e)

    appearance = row.get("appearance", "")
    tstamp = row.get("tstamp", "")
    ulcers_ans = row.get("ulcers", "")

    # set default return status to "no alert/0"
    update = 1

    if appearance in ["37c", "37d"]:
        update = 2
    elif other_row is not None and isinstance(other_row, dict):
        level = other_row.get("level", "")
        tstamp2 = other_row.get("tstamp", tstamp)

        t1 = get_datetime_value_from_string(tstamp)
        t2 = get_datetime_value_from_string(tstamp2)
        difference = t1 - t2
        time_diff = difference.total_seconds() / 3600.0

        if (
            ulcers_ans == "Yes"
            and level in ["12b", "12c", "12d"]
            and (0 <= time_diff <= 48)
        ):
            update = 2

    return update


def survey_dialysis(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_dialysis Table
    2. Inserts Dialysis Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""
    params = (
        req_body["submitted_by"],
        req_body["dizzy"],
        req_body["passedout"],
        req_body["cramping"],
        req_body["headaches"],
        req_body["nausea"],
        req_body["chestpain"],
        req_body["swelling"],
        req_body["breath"],
        req_body["weight"],
        req_body["other"],
        created_time,
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Dialysis Symptom \n------\n"
        f"Dizzy/Lightheaded: {req_body['dizzy']}\n"
        f"Passed out: {req_body['passedout']}\n"
        f"Cramping: {req_body['cramping']}\n"
        f"Headaches: {req_body['headaches']}\n"
        f"Nausea/Vomiting: {req_body['nausea']}\n"
        f"Chest pain: {req_body['chestpain']}\n"
        f"Leg Swelling: {req_body['swelling']}\n"
        f"Shortness of breath: {req_body['breath']}\n"
        f"Weight gain: {req_body['weight']}\n"
        f"Other symptoms: {req_body['other']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_DIALYSIS, params)
            inserted_row_id = cursor.lastrowid

            symptoms_insert_params = (
                req_body["patient_internal_id"],
                info_text_data,
                req_body["submitted_by"],
                created_time,
                flag_read,
                "Dialysis Symptom",
                inserted_row_id,
                req_body["submitter_internal_id"],
            )

            with carex_cnx.cursor() as carex_cursor:
                carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                symptom_id = carex_cursor.lastrowid
                insert_symptom_notification(
                    "Dialysis Symptom",
                    symptom_id,
                    req_body["patient_internal_id"],
                    req_body["submitter_internal_id"],
                    req_body["submitted_by"],
                    flag_read,
                    created_time,
                )
                carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_urinary(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_urinary Table
    2. Inserts Urinary Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["submitted_by"],
        req_body["report"],
        get_string_from_input(req_body["symptons_1"]),
        get_string_from_input(req_body["symptons_2"]),
        get_string_from_input(req_body["symptons_3"]),
        get_string_from_input(req_body["pain"]),
        get_string_from_input(req_body["pain_where"]),
        req_body["kidney_stone"],
        get_string_from_input(req_body["kidney_stone_when"]),
        get_string_from_input(req_body["kidney_stone_duration"]),
        req_body["kidney_stone_passed"],
        req_body["kidney_stone_passed_when"],
        req_body["kidney_stone_removed"],
        get_string_from_input(req_body["kidney_stone_removed_when"]),
        created_time,
        req_body["patient_internal_id"],
    )

    info_text_data = "Urinary Symptoms \n------\n"

    if req_body["symptons_1"]:
        info_text_data = f"{info_text_data}Symptoms reported: {get_string_from_input(req_body['symptons_1'])}\n"

    if req_body["symptons_2"]:
        info_text_data = f"{info_text_data}UTI Symptoms: {get_string_from_input(req_body['symptons_2'])}\n"

    if req_body["symptons_3"]:
        info_text_data = f"{info_text_data}Alert symptoms: {get_string_from_input(req_body['symptons_3'])}\n"

    if req_body["pain_where"]:
        info_text_data = f"{info_text_data}Pain (location): {get_string_from_input(req_body['pain_where'])}\n"

    if req_body["kidney_stone_when"]:
        info_text_data = f"{info_text_data}Recent Stone Symptoms: {get_string_from_input(req_body['kidney_stone_when'])}\n"

    if req_body["kidney_stone_duration"]:
        info_text_data = f"{info_text_data}Stone history: {get_string_from_input(req_body['kidney_stone_duration'])}\n"

    if req_body["kidney_stone_passed_when"]:
        info_text_data = (
            f"{info_text_data}Passed Stone: {req_body['kidney_stone_passed_when']}\n"
        )

    if req_body["kidney_stone_removed_when"]:
        info_text_data = f"{info_text_data}Stone procedure: {get_string_from_input(req_body['kidney_stone_removed_when'])}\n"

    if req_body["submitted_by"]:
        info_text_data = f"{info_text_data}Submitted_by: {req_body['submitted_by']}"

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_URINARY, params)
            inserted_row_id = cursor.lastrowid

            symptoms_insert_params = (
                req_body["patient_internal_id"],
                info_text_data,
                req_body["submitted_by"],
                created_time,
                flag_read,
                "Urinary Symptoms",
                inserted_row_id,
                req_body["submitter_internal_id"],
            )

            with carex_cnx.cursor() as carex_cursor:
                carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                symptom_id = carex_cursor.lastrowid
                insert_symptom_notification(
                    "Urinary Symptom",
                    symptom_id,
                    req_body["patient_internal_id"],
                    req_body["submitter_internal_id"],
                    req_body["submitted_by"],
                    flag_read,
                    created_time,
                )
                carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def get_bp_vital_signs_info_text(info_text_data, bp_taken_date, req_body):
    info_text = info_text_data

    if bp_taken_date:
        info_text = f"{info_text}BP taken on: {bp_taken_date.strftime('%m/%d/%Y')}\n"

    if req_body["bp_taken_time"]:
        info_text = f"{info_text}When: {req_body['bp_taken_time']}\n"

    if req_body["bp_posture"]:
        info_text = f"{info_text}Posture: {req_body['bp_posture']}\n"

    if req_body["bp_comments"]:
        info_text = f"{info_text}BP symptoms or comments: {get_string_from_input(req_body['bp_comments'])}\n"

    if req_body["am_systolic_top"]:
        info_text = f"{info_text}AM syst: {req_body['am_systolic_top']}\n"

    if req_body["am_diastolic_bottom"]:
        info_text = f"{info_text}AM dias: {req_body['am_diastolic_bottom']}\n"

    if req_body["pm_systolic_top"]:
        info_text = f"{info_text}PM syst: {req_body['pm_systolic_top']}\n"

    if req_body["pm_diastolic_bottom"]:
        info_text = f"{info_text}PM dias: {req_body['pm_diastolic_bottom']}\n"

    return info_text


def get_vital_signs_info_text(
    req_body, bp_taken_date, hr_taken_date, weight_taken_date
):
    """
    Returns Info Text for Vitals signs symptom reported
    """
    info_text_data = "Vital Signs \n------\n"

    info_text_data = get_bp_vital_signs_info_text(
        info_text_data=info_text_data, bp_taken_date=bp_taken_date, req_body=req_body
    )

    if hr_taken_date:
        info_text_data = (
            f"{info_text_data}HR taken on: {hr_taken_date.strftime('%m/%d/%Y')}\n"
        )

    if req_body["heart_rate"]:
        info_text_data = f"{info_text_data}HR: {req_body['heart_rate']}\n"

    if weight_taken_date:
        info_text_data = f"{info_text_data}Weight taken on: {weight_taken_date.strftime('%m/%d/%Y')}\n"

    if req_body["weight_pounds"]:
        info_text_data = f"{info_text_data}Wt (lb): {req_body['weight_pounds']}\n"

    if req_body["weight_kilograms"]:
        info_text_data = f"{info_text_data}Wt (kg): {req_body['weight_kilograms']}\n"

    if req_body["submitted_by"]:
        info_text_data = f"{info_text_data}Submitted_by: {req_body['submitted_by']}"

    return info_text_data


def survey_vital(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_vital Table
    2. Inserts Vital Signs Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    bp_taken_date = None
    hr_taken_date = None
    weight_taken_date = None
    flag_read = 1
    info_text_data = ""
    if req_body["bp_report"] == "Yes":
        bp_taken_date = (
            created_time
            if req_body["bp_taken_when"] == "Taken today"
            else datetime.strptime(req_body["bp_taken_date"], "%m/%d/%Y %H:%M:%S")
            if req_body["bp_taken_date"]
            else None
        )
    if req_body["hr_report"] == "Yes":
        hr_taken_date = (
            created_time
            if req_body["hr_taken_when"] == "Taken today"
            else datetime.strptime(req_body["hr_taken_date"], "%m/%d/%Y %H:%M:%S")
            if req_body["hr_taken_date"]
            else None
        )
    if req_body["weight_report"] == "Yes":
        weight_taken_date = (
            created_time
            if req_body["weight_taken_when"] == "Taken today"
            else datetime.strptime(req_body["weight_taken_date"], "%m/%d/%Y %H:%M:%S")
            if req_body["weight_taken_date"]
            else None
        )

    params = (
        req_body["submitted_by"],
        req_body["bp_report"],
        req_body["bp_taken_when"],
        bp_taken_date,
        req_body["bp_taken_time"],
        req_body["bp_posture"],
        get_string_from_input(req_body["bp_comments"]),
        req_body["am_systolic_top"],
        req_body["am_diastolic_bottom"],
        req_body["pm_systolic_top"],
        req_body["pm_diastolic_bottom"],
        req_body["hr_report"],
        req_body["hr_taken_when"],
        hr_taken_date,
        req_body["heart_rate"],
        req_body["weight_report"],
        req_body["weight_taken_when"],
        weight_taken_date,
        req_body["weight_scale"],
        req_body["weight_pounds"],
        req_body["weight_kilograms"],
        created_time,
        req_body["patient_internal_id"],
    )

    info_text_data = get_vital_signs_info_text(
        req_body=req_body,
        bp_taken_date=bp_taken_date,
        hr_taken_date=hr_taken_date,
        weight_taken_date=weight_taken_date,
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_VITALS, params)
            if (
                req_body["bp_report"] != "No"
                or req_body["hr_report"] != "No"
                or req_body["weight_report"] != "No"
            ):
                inserted_row_id = cursor.lastrowid

                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Vital Signs",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Vital Sign",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.info("Error in SQL")
        logger.error(traceback.format_exc())
        logger.error(str(err))
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_ulcers(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_ulcers Table
    2. Inserts Ulcer Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["ulcers"],
        get_string_from_input(req_body["location"]),
        req_body["size"],
        req_body["appearance"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Ulcers \n------\n"
        f"Location: {get_string_from_input(req_body['location'])}\n"
        f"Size: {req_body['size']}\n"
        f"Appearance: {req_body['appearance']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_ULCERS, params)
            if req_body["ulcers"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_ULCERS,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_ulcers(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Ulcers",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Ulcer",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_mood(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_mood Table
    2. Inserts Mood Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["mood"],
        req_body["lack_interest"],
        req_body["feeling_down"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Mood Impairment\n------\n"
        f"Lack interest: {req_body['lack_interest']}\n"
        f"Feeling down: {req_body['feeling_down']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_MOOD, params)
            if req_body["mood"] != "No":
                inserted_row_id = cursor.lastrowid

                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Mood Impairment",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Mood Impairment",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_appetite(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_appetite Table
    2. Inserts Appetite Impairment Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["appetite"],
        req_body["level"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Appetite Impairment\n------\n"
        f"Severity: {req_body['level']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_APPETITE, params)
            if req_body["appetite"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_APPETITE_IMPAIRMENT,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_appetite_impairment(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Appetite Impairment",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Appetite Impairment",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_lightheadedness(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_lightheadedness Table
    2. Inserts Lightheadedness Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["lightheadedness"],
        get_string_from_input(req_body["level"]),
        req_body["frequency"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Lightheadedness \n------\n"
        f"Occurance: {req_body['lightheadedness']}\n"
        f"Severity: {get_string_from_input(req_body['level'])}\n"
        f"Frequency: {req_body['frequency']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_LIGHTHEADEDNESS, params)
            if req_body["lightheadedness"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_LIGHTHEADEDNESS,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_light_headedness(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Lightheadedness",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Lightheadedness",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_pain(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_pain Table
    2. Inserts Aches/Pain Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["pain"],
        req_body["level"],
        get_string_from_input(req_body["location"]),
        req_body["frequency"],
        req_body["length"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Aches/Pain \n------\n"
        f"Severity: {req_body['level']}\n"
        f"Location: {get_string_from_input(req_body['location'])}\n"
        f"Frequency: {req_body['frequency']}\n"
        f"Length: {req_body['length']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_PAIN, params)
            if req_body["pain"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_ACHES_PAIN,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_aches_pain(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Aches Pain",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Aches Pain",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_chestpain(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_chestpain Table
    2. Inserts Chest Pain Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["chestpain"],
        req_body["recentpain"],
        req_body["restpain"],
        req_body["level"],
        get_string_from_input(req_body["type"]),
        req_body["length"],
        get_string_from_input(req_body["worse"]),
        get_string_from_input(req_body["better"]),
        req_body["frequency"],
        req_body["submitted_by"],
        created_time,
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Chest Pain \n------\n"
        f"Most recent episode: {req_body['recentpain']}\n"
        f"Pain at Rest: {req_body['restpain']}\n"
        f"Severity: {req_body['level']}\n"
        f"Type: {get_string_from_input(req_body['type'])}\n"
        f"Duration: {req_body['length']}\n"
        f"Symptoms worse when: {get_string_from_input(req_body['worse'])}\n"
        f"Symptoms better when: {get_string_from_input(req_body['better'])}\n"
        f"Frequency: {req_body['frequency']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_CHESTPAIN, params)
            if req_body["chestpain"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_CHESTPAIN,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_chest_pain(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Chest Pain",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Chest Pain",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_weightchange(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_weightchange Table
    2. Inserts Weight Change Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["submitted_by"],
        req_body["report"],
        req_body["period"],
        req_body["gained_lost"],
        req_body["lb_kg"],
        req_body["change_in_lb"],
        req_body["change_in_kg"],
        created_time,
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Weight Change \n------\n"
        f"Reported over: {req_body['period']}\n"
        f"Weight: {req_body['gained_lost']}\n"
        f"Amount: {req_body['change_in_lb']}{req_body['change_in_kg']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_WEIGHTCHANGE, params)
            if req_body["report"] != "No":
                inserted_row_id = cursor.lastrowid

                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Weight Change",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Weight Change",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_swelling(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_swelling Table
    2. Inserts Leg Swelling Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["swelling"],
        req_body["level"],
        req_body["worse"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Leg swelling \n------\n"
        f"Severity: {req_body['level']}\n"
        f"Getting worse: {req_body['worse']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_SWELLING, params)
            if req_body["swelling"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_LEG_SWELLING,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_leg_swelling(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Leg swelling",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Leg swelling",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_breath(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_breath Table
    2. Inserts Shortness of Breath Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["breath"],
        req_body["level"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Shortness of Breath \n------\n"
        f"Causes: {req_body['level']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_BREATH, params)
            if req_body["breath"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_SHORTNESS_OF_BREATH,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_shortness_of_breath(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Shortness of Breath",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Shortness of Breath",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_fatigue(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_fatigue Table
    2. Inserts Fatigue Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["fatigue"],
        req_body["level"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Fatigue \n------\n"
        f"Severity: {req_body['level']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_FATIGUE, params)
            if req_body["fatigue"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_FATIGUE,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_fatigue(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Fatigue",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Fatigue",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_fever(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_fever Table
    2. Inserts Fever Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["fever"],
        req_body["level"],
        req_body["frequency"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Fever \n------\n"
        f"Severity: {req_body['level']}\n"
        f"Frequency: {req_body['frequency']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_FEVER, params)
            if req_body["fever"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_FEVER,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_fever(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Fever",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Fever",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_nausea(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_nausea Table
    2. Inserts Nausea Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["nausea"],
        req_body["level"],
        req_body["frequency"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Nausea \n------\n"
        f"Severity: {req_body['level']}\n"
        f"Frequency: {req_body['frequency']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_NAUSEA, params)
            if req_body["nausea"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_NAUSEA,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_nausea(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Nausea",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Nausea",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def survey_falls(req_body):
    """
    This Function:
    1. Inserts Input Symptom data into survey_falls Table
    2. Inserts Falls Symptom into mi_symptoms Table
    3. Inserts Notification for Inserted Symptom
    """
    created_time = datetime.utcnow()
    flag_read = 1
    info_text_data = ""

    params = (
        req_body["falls"],
        req_body["level"],
        created_time,
        req_body["submitted_by"],
        req_body["patient_internal_id"],
    )

    info_text_data = (
        "Falls \n------\n"
        f"Frequency: {req_body['level']}\n"
        f"Submitted_by: {req_body['submitted_by']}"
    )

    try:
        with mlprep_cnx.cursor() as cursor:
            cursor.execute(INSERT_SURVEY_FALLS, params)
            if req_body["falls"] != "No":
                inserted_row_id = cursor.lastrowid
                response_dict = read_as_dict(
                    mlprep_cnx,
                    GET_NORMALIZED_FALLS,
                    (inserted_row_id),
                    fetchone=True,
                )
                flag_read = calculate_alert_falls(response_dict)
                symptoms_insert_params = (
                    req_body["patient_internal_id"],
                    info_text_data,
                    req_body["submitted_by"],
                    created_time,
                    flag_read,
                    "Falls",
                    inserted_row_id,
                    req_body["submitter_internal_id"],
                )

                with carex_cnx.cursor() as carex_cursor:
                    carex_cursor.execute(INSERT_SYMPTOMS_TABLE, symptoms_insert_params)
                    symptom_id = carex_cursor.lastrowid
                    insert_symptom_notification(
                        "Fall",
                        symptom_id,
                        req_body["patient_internal_id"],
                        req_body["submitter_internal_id"],
                        req_body["submitted_by"],
                        flag_read,
                        created_time,
                    )
                    carex_cnx.commit()
            mlprep_cnx.commit()
            return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


survey_function_map = {
    "falls": survey_falls,
    "nausea": survey_nausea,
    "fever": survey_fever,
    "fatigue": survey_fatigue,
    "breath": survey_breath,
    "swelling": survey_swelling,
    "weightchange": survey_weightchange,
    "chestpain": survey_chestpain,
    "pain": survey_pain,
    "lightheadedness": survey_lightheadedness,
    "appetite": survey_appetite,
    "mood": survey_mood,
    "ulcers": survey_ulcers,
    "vital": survey_vital,
    "urinary": survey_urinary,
    "dialysis": survey_dialysis,
}


def lambda_handler(event, context):
    """
    Handler file for misc service
    """
    auth_user = event["requestContext"].get("authorizer")
    req_body = json.loads(event["body"])
    logged_in_user = find_user_by_external_id(carex_cnx, auth_user["userSub"])
    if logged_in_user:
        req_body["submitter_internal_id"] = logged_in_user["internal_id"]
    path = event["path"].split("/")
    symptom_type = path[-1]
    response = {}
    status_code = (
        HTTPStatus.NOT_FOUND
    )  # Default value as Not Found if the path isnt correct

    survey_function = survey_function_map.get(symptom_type)
    if survey_function:
        status_code, response = survey_function(req_body)

    return {
        "statusCode": status_code,
        "body": json.dumps(response),
        "headers": get_headers(),
    }
