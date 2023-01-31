import json
import logging
from datetime import datetime, timedelta

from http import HTTPStatus
import boto3
import pymysql
from notification import insert_to_medication_notifications_table
from shared import (
    encrypt,
    find_user_by_external_id,
    find_user_by_internal_id,
    get_db_connect,
    get_headers,
    get_phi_data_from_internal_id,
    read_as_dict,
)
from sqls.medication import (
    GET_MEDICATION,
    GET_MEDICATION_BY_ID,
    GET_NETWORK_PROVIDERS,
    INSERT_MEDICATION,
    UPDATE_MEDICATION,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
connection = get_db_connect()
dynamodb = boto3.resource("dynamodb")


def save_medication(cnx, patient_id, med_data, logged_in_user_id):
    """
    Insert the medication to database
    """
    created_time = datetime.utcnow()
    if med_data.get("RecordId"):
        params = {
            "modified_by": logged_in_user_id,
            "upd_date": created_time,
            "status": "M",
            "ids": tuple([med_data["RecordId"]]),
            "discontinue_reason": None,
        }
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_MEDICATION, params)
            cnx.commit()
            medication_row = get_medication_row(cnx, med_data.get("RecordId"))
            type = "modified"
            insert_medication_notification_for_network_providers(
                cnx, type, medication_row
            )

    med_reasons = ""
    if med_data.get("MedReasons"):
        med_reasons = ",".join(med_data["MedReasons"])
    params = {
        "patient_id": patient_id,
        "product_id": med_data["ProductId"],
        "product_short_name": med_data["ProductShortName"].replace("\\", ""),
        "product_long_name": med_data["ProductLongName"].replace("\\", ""),
        "quantity": med_data["Quantity"],
        "unit_strength": med_data["UnitStrength"],
        "unit_code": med_data["UnitCode"],
        "sig": med_data["Sig"],
        "prn": med_data["Prn"],
        "ingredient": str(med_data["Ingredient"]),
        "status": med_data["Status"],
        "created_by": med_data["CreatedBy"],
        "modified_by": med_data["CreatedBy"],
        "crt_date": created_time,
        "upd_date": created_time,
        "duration": med_data["Duration"],
        "info_from": med_data["InfoFrom"],
        "sig_extra_note": med_data["SigExtraNote"],
        "medication_reasons": med_reasons,
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_MEDICATION, params)
            medication_row_id = cursor.lastrowid
            cnx.commit()
            medication_row = {
                "id": medication_row_id,
                "patient_internal_id": patient_id,
                "product_id": med_data["ProductId"],
                "product_short_name": med_data["ProductShortName"].replace("\\", ""),
                "product_long_name": med_data["ProductLongName"].replace("\\", ""),
                "quantity": med_data["Quantity"],
                "unit_strength": med_data["UnitStrength"],
                "unit_code": med_data["UnitCode"],
                "sig": med_data["Sig"],
                "prn": med_data["Prn"],
                "ingredient": str(med_data["Ingredient"]),
                "status": med_data["Status"],
                "created_by": med_data["CreatedBy"],
                "modified_by": med_data["CreatedBy"],
                "create_time": created_time,
                "update_time": created_time,
                "duration": med_data["Duration"],
                "info_from": med_data["InfoFrom"],
                "sig_extra_note": med_data["SigExtraNote"],
                "medication_reasons": med_reasons,
                "discontinue_reasons": None,
            }
            type = "added"
            insert_medication_notification_for_network_providers(
                cnx, type, medication_row
            )
        return 200, "Saved Successfully"
    except pymysql.MySQLError as err:
        logger.error(err)
        return 500, err


def delete_medication(cnx, rec_id, user_id):
    """
    Soft Delete Medication for a patient from DB
    """
    rec = read_as_dict(cnx, GET_MEDICATION_BY_ID, {"id": rec_id}, fetchone=True)
    now = datetime.utcnow()
    if isinstance(rec, dict) and not (
        now - timedelta(hours=24) <= rec["create_time"] <= now
    ):
        return 400, "Medication can't be deleted"
    params = {
        "modified_by": user_id,
        "upd_date": now,
        "discontinue_reason": None,
        "status": "D",
        "ids": tuple([rec_id]),
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_MEDICATION, params)
            cnx.commit()
            medication_row = get_medication_row(cnx, rec_id)
            type = "deleted"
            insert_medication_notification_for_network_providers(
                cnx, type, medication_row
            )

            return 200, "Medication Deleted Successfully"
    except pymysql.MySQLError as err:
        return 500, str(err)


def update_medication(
    cnx, patient_id, product_id, user_id, status, discontinue_reason=None
):
    """
    Discontinue Medication assigned to a patient
    """
    upd_time = datetime.utcnow()
    record = read_as_dict(
        cnx, GET_MEDICATION, {"product_id": product_id, "patient_id": patient_id}
    )

    rec_ids = [med["id"] for med in record] if record else []
    params = {
        "modified_by": user_id,
        "upd_date": upd_time,
        "status": status,
        "ids": tuple(rec_ids),
        "discontinue_reason": json.dumps(discontinue_reason)
        if discontinue_reason
        else None,
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_MEDICATION, params)
            cnx.commit()
            id = rec_ids[0]
            medication_row = get_medication_row(cnx, id)
            type = "discontinued"
            insert_medication_notification_for_network_providers(
                cnx, type, medication_row
            )

        return 200, "Medication Stopped Successfully"
    except pymysql.MySQLError as err:
        return 500, err


def lambda_handler(event, context):
    """
    Save Medication Handler
    """
    patient_id = event["pathParameters"].get("patient_id")
    product_id = event["pathParameters"].get("product_id", None)
    auth_user = event["requestContext"].get("authorizer")
    user = find_user_by_external_id(
        connection, auth_user["userSub"], auth_user["userRole"]
    )
    status_code = HTTPStatus.BAD_REQUEST
    result = {}
    if user:
        if "save" in event["path"].split("/"):
            med_data = json.loads(event["body"])
            status_code, result = save_medication(
                connection, patient_id, med_data["Medication"], user["internal_id"]
            )
        elif "stop" in event["path"].split("/"):
            form_data = json.loads(event["body"])
            if form_data.get("DiscontinueReason"):
                discontinue_reasons = form_data["DiscontinueReason"]
            else:
                discontinue_reasons = None
            status_code, result = update_medication(
                connection,
                patient_id,
                product_id,
                user["internal_id"],
                "S",
                discontinue_reasons,
            )
        elif "delete" in event["path"].split("/"):
            med_id = event["pathParameters"].get("med_id")
            status_code, result = delete_medication(
                connection, med_id, user["internal_id"]
            )
            print(status_code, result)
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }


def get_medication_row(cnx, id):
    """
    Returns Medication data based on DB id from input
    """
    medication_row = read_as_dict(
        connection=cnx, query=GET_MEDICATION_BY_ID, params={"id": id}, fetchone=True
    )
    return medication_row


def get_medication_notification_details(
    medicine_name,
    created_by,
    patient_internal_id,
    patient_name,
    quantity,
    unit_code,
    sig,
    user_name=None,
    user_name_degree=None,
    type=None,
):
    """
    Generates notification_details for the medication operation based on input
    """
    if created_by == patient_internal_id:
        return (
            f"Medication has been {type} for {patient_name} by {patient_name}"
            f" :{medicine_name}({quantity}{unit_code},{sig})"
        )
    if user_name_degree:
        return (
            f"Medication has been {type} for {patient_name} by {user_name},{user_name_degree}"
            f" :{medicine_name}({quantity}{unit_code},{sig})"
        )
    return (
        f"Medication has been {type} for {patient_name} by {user_name}"
        f" :{medicine_name}({quantity}{unit_code},{sig})"
    )


def get_user_name_and_degree(user_id):
    """
    Returns Username and degree from dynamodb phi_data for the user's internal_id
    """
    user_name_phi_data = get_phi_data_from_internal_id(connection, dynamodb, user_id)

    user_name = (
        f"{user_name_phi_data['first_name']} {user_name_phi_data['last_name']}"
        if user_name_phi_data
        else ""
    )

    submitter_user_data = find_user_by_internal_id(connection, user_id)

    user_name_degree = (
        submitter_user_data["degree"]
        if submitter_user_data and "degree" in submitter_user_data
        else ""
    )
    return user_name, user_name_degree


def insert_medication_notification_for_network_providers(
    cnx, type=None, medication_row=None
):
    """
    This Function:
    1. Gets list of network users for the patient
    2. Generates appropriate notification_details
    3. Inserts notification for each network user in medication_notifications
    """
    network_providers = (
        read_as_dict(
            cnx,
            GET_NETWORK_PROVIDERS,
            {"patient_internal_id": medication_row["patient_internal_id"]},
        )
        if medication_row
        else []
    )

    network_user_internal_ids = []
    if network_providers:
        for user in network_providers:
            if user["provider_internal_id"]:
                network_user_internal_ids.append(user["provider_internal_id"])
            elif user["caregiver_internal_id"]:
                network_user_internal_ids.append(user["caregiver_internal_id"])

    if medication_row:
        patient_phi_data = get_phi_data_from_internal_id(
            connection, dynamodb, medication_row["patient_internal_id"]
        )
        patient_name = (
            (f"{patient_phi_data['first_name']} {patient_phi_data['last_name']}")
            if patient_phi_data
            else ""
        )

        if medication_row["patient_internal_id"] != medication_row["modified_by"]:
            user_name, user_name_degree = get_user_name_and_degree(
                medication_row["modified_by"]
            )

            notification_details = get_medication_notification_details(
                type=type,
                medicine_name=medication_row["product_short_name"].replace("\\", ""),
                created_by=medication_row["modified_by"],
                patient_internal_id=medication_row["patient_internal_id"],
                patient_name=patient_name,
                quantity=medication_row["quantity"],
                sig=medication_row["sig"],
                unit_code=medication_row["unit_code"],
                user_name=user_name,
                user_name_degree=user_name_degree,
            )

        else:
            notification_details = get_medication_notification_details(
                type=type,
                medicine_name=medication_row["product_short_name"].replace("\\", ""),
                created_by=medication_row["modified_by"],
                patient_internal_id=medication_row["patient_internal_id"],
                patient_name=patient_name,
                quantity=medication_row["quantity"],
                sig=medication_row["sig"],
                unit_code=medication_row["unit_code"],
            )

        for user in network_user_internal_ids:
            insert_to_medication_notifications_table(
                cnx=cnx,
                patient_internal_id=medication_row["patient_internal_id"],
                medication_row_id=medication_row["id"],
                notifier_internal_id=user,
                level=1,
                notification_details=encrypt(notification_details),
                created_on=datetime.utcnow(),
                created_by=medication_row["created_by"],
                updated_on=datetime.utcnow(),
                updated_by=medication_row["created_by"],
                notification_status=1,
            )

        return "saved successfully"
    return "medication row doesnt exist"
