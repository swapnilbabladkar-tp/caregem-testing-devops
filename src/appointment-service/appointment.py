import json
import logging
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from custom_exception import GeneralException
from shared import (
    find_user_by_external_id,
    find_user_by_internal_id,
    get_db_connect,
    get_headers,
    get_phi_data,
    get_phi_data_list,
    read_as_dict,
)
from sqls.appointment import (
    GET_APPOINTMENT_BY_ID,
    GET_APPOINTMENT_BY_PAT_PRV_ID,
    INSERT_APPOINTMENT,
    LIST_APPOINTMENT,
    SAME_NETWORK,
    UPDATE_APPOINTMENT,
)

dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def in_same_network(cnx, provider_internal_id, patient_id):
    """
    Function returns boolean value based on if
    the selected provider and patient are in the same network
    """
    result = read_as_dict(
        cnx, SAME_NETWORK, {"user_id": provider_internal_id, "patient_id": patient_id}
    )
    return bool(result)


def get_appointment(cnx, appointment_id):
    """
    Get Appointment data based on input appointment id
    """
    return read_as_dict(
        cnx, GET_APPOINTMENT_BY_ID, {"id": appointment_id}, fetchone=True
    )


def set_appointment(cnx, patient_internal_id, provider_internal_id, date_time):
    """
    This function :
    1. Checks if an appointment exists between the selected patient and provider
    2. If exists, it updates the appointment date to current date
    3. Inserts new appointment if it doesnt exist
    """
    params = {"patient_id": patient_internal_id, "provider_id": provider_internal_id}
    appointment = read_as_dict(
        cnx, GET_APPOINTMENT_BY_PAT_PRV_ID, params, fetchone=True
    )
    current_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    if appointment:
        logger.info("Updating The Appointment")
        appointment_id = appointment["id"]
        appointment["date_time"] = appointment["date_time"].strftime("%Y-%m-%d %H:%M")
        if appointment["date_time"] == date_time:
            logger.info("Not updating appointment.")
            return appointment
        params = {"active": 0, "upd_dt": current_date, "id": appointment_id}
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_APPOINTMENT, params)
            cnx.commit()
    date_time = datetime.strptime(date_time, "%Y-%m-%d %H:%M")
    params = {
        "patient_id": patient_internal_id,
        "provider_id": provider_internal_id,
        "date_time": date_time,
        "active": 1,
        "crt_dt": current_date,
        "upd_dt": current_date,
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_APPOINTMENT, params)
            appointment_id = cursor.lastrowid
            cnx.commit()
        return HTTPStatus.OK, {
            "id": appointment_id,
            "patient_internal_id": int(patient_internal_id),
            "provider_internal_id": int(provider_internal_id),
            "date_time": date_time.strftime("%Y-%m-%d %H:%M"),
            "active": 1,
        }
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def create_appointment(
    cnx, auth_user, patient_internal_id, provider_internal_id, date_time
):
    """
    Create An appointment
    """
    patient = find_user_by_internal_id(cnx, patient_internal_id, "patient")
    provider = find_user_by_internal_id(cnx, provider_internal_id, "providers")
    if not patient or not provider:
        logger.error("Requested patient or Provider Doesn't exist")
        return HTTPStatus.BAD_REQUEST, []
    # Only patients, caregivers or physicians can schedule an appointment.
    if auth_user["userRole"] not in [
        "patient",
        "caregiver",
        "physician",
        "nurse",
        "case_manager",
    ]:
        logger.error("Logged user cannot schedule an appointment")
        return HTTPStatus.BAD_REQUEST, []
    # If user is a patient, check if they are creating an appointment for themself.
    if (
        auth_user["userRole"] == "patient"
        and auth_user["internal_id"] != patient["internal_id"]
    ):
        logger.error(
            "Patient is trying to create an appointment on behalf of another patient"
        )
        return HTTPStatus.BAD_REQUEST, []
    # If user is a provider, check if they are creating an appointment for themself.
    if (auth_user["userRole"] in ["physician", "nurse", "case_manager"]) and (
        auth_user["internal_id"] != provider["internal_id"]
    ):
        logger.error(
            "Physician is trying to create an appointment on behalf of another provider"
        )
        return HTTPStatus.BAD_REQUEST, []
    # Check if the provider can have access to the patient's details.
    if not in_same_network(cnx, provider_internal_id, patient["id"]):
        logger.error("Requested provider and patient are not in the same network")
        return HTTPStatus.BAD_REQUEST, []

    return set_appointment(cnx, patient_internal_id, provider_internal_id, date_time)


def update_appointment(cnx, appointment_id):
    """
    Update Appointment Data
    """
    current_datetime_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    params = {"active": 0, "upd_dt": current_datetime_utc, "id": appointment_id}
    try:
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_APPOINTMENT, params)
            cnx.commit()
        return HTTPStatus.OK, "Appointment Updated Successfully"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def remove_appointment(cnx, auth_user, appointment_id):
    """
    Remove Appointment
    """
    appointment = get_appointment(cnx, appointment_id)
    if not appointment:
        logger.error("Requested appointment id not Found")
        return HTTPStatus.BAD_REQUEST, []
    # If user is a Caregiver, check if they are removing an appointment for them self.
    if (auth_user["userRole"] == "patient") and (
        auth_user["internal_id"] != appointment["patient_internal_id"]
    ):
        logging.error(
            "Patient is trying to remove an appointment on behalf of another patient"
        )
        return HTTPStatus.BAD_REQUEST, []

    # If user is a patient, check if they are removing an appointment behalf of a patient outside their network
    if (auth_user["userRole"] == "caregiver") and (
        not in_same_network(
            cnx, auth_user["internal_id"], appointment["patient_internal_id"]
        )
    ):
        logging.error(
            "Caregiver is trying to remove an appointment on behalf of a patient outside their network"
        )
        return HTTPStatus.BAD_REQUEST, []

    # If user is a physician, check if they are removing an behalf of another provider.
    if (auth_user["userRole"] in ["physician", "nurse", "case_manager"]) and (
        auth_user["internal_id"] != appointment["provider_internal_id"]
    ):
        logging.error(
            "Physician is trying to remove an appointment on behalf of another provider"
        )
        return HTTPStatus.BAD_REQUEST, []

    code, result = update_appointment(cnx, appointment_id)
    logger.info(result)
    if code == HTTPStatus.OK:
        return HTTPStatus.OK, {
            "id": appointment["id"],
            "patient_internal_id": int(appointment["patient_internal_id"]),
            "provider_internal_id": int(appointment["provider_internal_id"]),
            "date_time": appointment["date_time"].strftime("%Y-%m-%d %H:%M"),
            "active": 0,
        }
    return code, result


def list_appointment(cnx, patient_internal_id):
    """
    List Appointment
    """
    try:
        appointments = read_as_dict(
            cnx, LIST_APPOINTMENT, {"patient_id": patient_internal_id}
        )
        patient = find_user_by_internal_id(cnx, patient_internal_id, "patient")
        patient_details = get_phi_data(patient["external_id"], dynamodb)
        provider_external_ids = [provider["external_id"] for provider in appointments]
        phi_data_list = get_phi_data_list(provider_external_ids, dynamodb)
        for appointment in appointments:
            prv_data = phi_data_list[appointment["external_id"]]
            appointment["prv_name"] = (
                prv_data["first_name"] + " " + prv_data["last_name"]
            )
            appointment["patient_name"] = (
                patient_details["first_name"] + " " + patient_details["last_name"]
            )
            appointment["date_time"] = appointment["date_time"].strftime(
                "%Y-%m-%d %H:%M"
            )
            del appointment["external_id"]
        return HTTPStatus.OK, appointments
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def lambda_handler(event, context):
    """
    Handler Function.
    """
    # auth_user = get_logged_in_user(event["headers"]["Authorization"])
    auth_user = event["requestContext"].get("authorizer")
    auth_user.update(
        find_user_by_external_id(
            connection, auth_user["userSub"], auth_user["userRole"]
        )
    )
    if "schedule" in event["path"].split("/"):
        form_data = json.loads(event["body"])
        patient_internal_id = form_data.get("patient_internal_id")
        provider_internal_id = form_data.get("provider_internal_id")
        date_time = form_data.get("date_time")
        status_code, result = create_appointment(
            connection, auth_user, patient_internal_id, provider_internal_id, date_time
        )
    elif "remove" in event["path"].split("/"):
        appointment_id = event["pathParameters"].get("appointment_id")
        status_code, result = remove_appointment(connection, auth_user, appointment_id)
    elif "list" in event["path"].split("/"):
        patient_id = event["pathParameters"].get("patient_id")
        status_code, result = list_appointment(connection, patient_id)
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
