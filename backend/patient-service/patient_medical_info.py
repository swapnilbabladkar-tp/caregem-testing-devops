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
from sqls.patient_queries import (
    caregiver_symptoms_query,
    patient_symptoms_query,
    provider_symptoms_query,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cnx = get_db_connect()


def get_symptoms_for_patient(cnx, patient_internal_id):
    """
    Returns Symptom data as a list of dict for the selected patient
    """
    symptoms_dict_list = read_as_dict(cnx, patient_symptoms_query, patient_internal_id)
    return symptoms_dict_list


def get_symptoms_for_caregiver(cnx, caregiver_internal_id, patient_internal_id):
    """
    Returns Symptom data as a list of dict for the selected patient
    if the caregiver is in the patient's network
    """
    symptoms_dict_list = read_as_dict(
        cnx, caregiver_symptoms_query, (patient_internal_id, caregiver_internal_id)
    )
    return symptoms_dict_list


def get_symptoms_for_provider(cnx, provider_internal_id, patient_internal_id):
    """
    Returns Symptom data as a list of dict for the selected patient
    if the provider is in the patient's network
    """
    symptoms_dict_list = read_as_dict(
        cnx, provider_symptoms_query, (patient_internal_id, provider_internal_id)
    )
    return symptoms_dict_list


def get_medical_info(patient_internal_id, external_id, role):
    """
    This function gets symptom data for the patient based on
    the role of the logged in user
    """
    try:
        user = find_user_by_external_id(cnx, external_id, role)
        if user:
            final_symptoms_list = []
            if role == "patient":
                logging.debug("Patient requested its own symptoms.")
                symptoms_dict_list = get_symptoms_for_patient(cnx, patient_internal_id)
            elif role == "caregiver":
                logging.debug("Caregiver requested patient's symptoms.")
                symptoms_dict_list = get_symptoms_for_caregiver(
                    cnx, user["internal_id"], patient_internal_id
                )
            else:
                logging.debug("Provider requested patient's symptoms.")
                symptoms_dict_list = get_symptoms_for_provider(
                    cnx, user["internal_id"], patient_internal_id
                )

            if symptoms_dict_list:
                for row in symptoms_dict_list:
                    item = dict()
                    item["enter_date"] = row["mi_symptoms_enter_date"].strftime(
                        "%m/%d/%Y %H:%M:%S"
                    )
                    item["flag_read"] = 0
                    item["id"] = row["mi_symptoms_id"]
                    item["info_blob"] = row["mi_symptoms_info_blob"]
                    item["info_text"] = (
                        row["mi_symptoms_info_text"].replace("\r", "\n")
                        if "\r" in row["mi_symptoms_info_text"]
                        else row["mi_symptoms_info_text"]
                    )
                    item["patient_id"] = row["mi_symptoms_patient_id"]
                    item["reportedBy"] = row["mi_symptoms_submitted_by"]
                    final_symptoms_list.append(item)
                return HTTPStatus.OK, final_symptoms_list
    except GeneralException as err:
        logger.exception(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err
    return HTTPStatus.INTERNAL_SERVER_ERROR, {"message": "Failed to fetch data"}


def lambda_handler(event, context):
    """
    The api will handle getting medical info for a patient
    """
    auth_user = event["requestContext"].get("authorizer")
    external_id = auth_user["userSub"]
    role = auth_user["userRole"]
    patient_internal_id = event["pathParameters"].get("patient_internal_id")
    user_data = find_user_by_external_id(cnx, external_id, role)
    status_code = HTTPStatus.NOT_FOUND
    user_result = {}
    is_allowed, result = check_user_access_for_patient_data(
        cnx=cnx,
        role=role,
        user_data=user_data,
        patient_internal_id=patient_internal_id,
    )
    if is_allowed and result and result["message"] == "Success":
        status_code, user_result = get_medical_info(
            patient_internal_id, external_id, role
        )
    else:
        status_code = HTTPStatus.BAD_REQUEST
        user_result = result
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
