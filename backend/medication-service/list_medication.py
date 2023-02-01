import ast
from http import HTTPStatus
import json
import logging

import boto3
from custom_exception import GeneralException
from med_utils import get_external_id_form_internal_id, med_dup_check
from shared import (
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data_list,
    read_as_dict,
    check_user_access_for_patient_data,
)
from sqls.medication import med_base_query

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()


def get_ingredient(ingredient, search_filter):
    """
    Eval Function to filter medication based on ingredients
    Returns True if search value is present in the ingredient list given as input
    """
    for ing in ingredient:
        if search_filter.lower() in ing["Name"].lower():
            return True


def filter_med_by_name(name, medication):
    """
    Filter medication list based on :
    1. Search Value being present in medication name
    2. Search Value being present in medication ingredient names
    """
    unique_ids = []
    filtered_med = []
    for rec in medication:
        if name.lower() in rec["ProductShortName"].lower() or get_ingredient(
            ast.literal_eval(rec["Ingredient"]), name
        ):
            if rec["RecordId"] not in unique_ids:
                unique_ids.append(rec["RecordId"])
                filtered_med.append(rec)
    return filtered_med


def get_med_base_result(cnx, patient_id, status, name_filter=None, med_reasons=None):
    """Get the medication Base Results."""
    query = med_base_query
    if med_reasons:
        conditions = " OR ".join(
            [
                "medication.medication_reasons like " + "'%%" + reason + "%%'"
                for reason in med_reasons
            ]
        )
        query = query + " AND " + "(" + conditions + ")"
    medication = read_as_dict(
        cnx, query, {"patient_id": patient_id, "status": tuple(status)}
    )
    if name_filter:
        medication = filter_med_by_name(name_filter, medication)
    response_dict = {}
    if not medication:
        return response_dict
    dup_list = []
    internal_ids = set()
    for med in medication:
        internal_ids.update([med["ModifiedBy"], med["CreatedBy"]])
    internal_ids = list(internal_ids)
    ext_int_id_mapping = get_external_id_form_internal_id(cnx, internal_ids)
    external_ids = list(ext_int_id_mapping.values())
    phi_data = get_phi_data_list(external_ids, dynamodb)
    try:
        for med in medication:
            if status == "A":
                dup_check_list = med_dup_check(
                    cnx, med["PatientId"], ast.literal_eval(med["Ingredient"]), False
                )
                med["isDuplicate"] = "1" if len(dup_check_list) > 1 else "0"
                dup_list.extend(dup_check_list)
            entered_by = phi_data[ext_int_id_mapping[med["CreatedBy"]]]
            modified_by = phi_data[ext_int_id_mapping[med["ModifiedBy"]]]
            med["CreatedBy"] = (
                entered_by.get("first_name") + " " + entered_by.get("last_name")
            )
            med["ModifiedBy"] = (
                modified_by.get("first_name") + " " + modified_by.get("last_name")
            )
            med["MedReasons"] = (
                med["MedReasons"].split(",") if med["MedReasons"] else []
            )
            med["Ingredient"] = ast.literal_eval(med["Ingredient"])
            med["DiscontinuedReason"] = (
                json.loads(med["DiscontinuedReason"])
                if med["DiscontinuedReason"]
                else []
            )
        response_dict["Duplication"] = [
            *{str(v["ProductId"]): v for v in dup_list}.values()
        ]
        response_dict["Medication"] = medication
        response_dict["PatientId"] = patient_id
        return response_dict
    except GeneralException as e:
        logger.exception(e)


def get_active_medication(cnx, patient_id, name_filter=None, med_reasons=None):
    """
    Returns the Active Medications for a patient
    """
    active_medication = get_med_base_result(
        cnx, patient_id, "A", name_filter, med_reasons
    )
    return active_medication


def get_stopped_medication(cnx, patient_id, name_filter=None, med_reasons=None):
    """
    Returns the Stopped Medication for a patient.
    """
    stopped_medication = get_med_base_result(
        cnx, patient_id, "S", name_filter, med_reasons
    )
    if stopped_medication:
        stopped_medication.pop("Duplication", None)
        stopped_medication.pop("PatientId", None)
    return stopped_medication


def lambda_handler(event, context):
    """Medication sig Handler"""
    auth_user = event["requestContext"].get("authorizer")
    external_id = auth_user["userSub"]
    role = auth_user["userRole"]
    user_data = find_user_by_external_id(connection, external_id, role)
    patient_id = event["pathParameters"].get("patient_id")
    query_params = (
        event["queryStringParameters"] if event["queryStringParameters"] else {}
    )
    name_filter = query_params.get("name_filter", None)
    med_reasons = (
        query_params["med_reasons"].split(",")
        if query_params.get("med_reasons")
        else None
    )
    is_allowed, access_result = check_user_access_for_patient_data(
        cnx=connection,
        role=role,
        user_data=user_data,
        patient_internal_id=patient_id,
    )
    if is_allowed and access_result and access_result["message"] == "Success":
        if "listactivemedication" in event["path"].split("/"):
            medication = get_active_medication(
                connection, patient_id, name_filter, med_reasons
            )
            status_code = HTTPStatus.OK
        else:
            medication = get_stopped_medication(
                connection, patient_id, name_filter, med_reasons
            )
            status_code = HTTPStatus.OK
    else:
        status_code = HTTPStatus.BAD_REQUEST
        medication = access_result
    return {
        "statusCode": status_code,
        "body": json.dumps(medication),
        "headers": get_headers(),
    }
