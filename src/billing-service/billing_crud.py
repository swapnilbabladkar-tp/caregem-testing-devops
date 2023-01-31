import json
import logging
import os
from datetime import datetime

import pymysql
import requests
from custom_exception import GeneralException
from dotenv import load_dotenv
from shared import (
    find_user_by_internal_id,
    get_db_connect,
    get_headers,
    get_phi_data,
    get_secret_manager,
    get_user_org_ids,
    read_as_dict,
    read_query,
)

load_dotenv()

cds_secret_id = os.getenv("CDS_SECRET_ID", "")

cds_cred = get_secret_manager(cds_secret_id)
host_cds = cds_cred["CDS_SERVER"]
token_cds = cds_cred["CDS_TOKEN"]

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cnx = get_db_connect()


def find_billing_by_patient_and_provider(cnx, patient_id, provider_id):
    """
    Returns all bills for the selected patient and provider
    """
    query = """ SELECT billing_detail.patient_internal_id   AS patientId,
                       billing_detail.id                    AS id,
                       billing_detail.provider_internal_id  AS providerId,
                       billing_detail.provider_name         AS providerName,
                       billing_detail.billing_diagnose_code AS diagnoses,
                       billing_detail.billing_charge_code   AS charges,
                       billing_detail.patient_location      AS patientLocation,
                       billing_detail.provider_location     AS providerLocation,
                       billing_detail.total_duration_billed AS currentMonthContactTime,
                       billing_detail.status                AS status
                FROM billing_detail
                WHERE patient_internal_id = %s
                AND provider_internal_id =%s
                ORDER BY date_of_service DESC"""
    bills = read_as_dict(cnx, query, (patient_id, provider_id))
    return bills if bills else []


def find_billing_by_patient_and_org(cnx, patient_id, org_ids):
    """
    Returns all bills in the input orgs for the selected patient
    """
    f_str = ",".join(["%s"] * len(org_ids))
    query = """ SELECT billing_detail.patient_internal_id   AS patientId,
                       billing_detail.id                    AS id,
                       billing_detail.provider_internal_id  AS providerId,
                       billing_detail.provider_name         AS providerName,
                       billing_detail.billing_diagnose_code AS diagnoses,
                       billing_detail.billing_charge_code   AS charges,
                       billing_detail.patient_location      AS patientLocation,
                       billing_detail.provider_location     AS providerLocation,
                       billing_detail.total_duration_billed AS currentMonthContactTime,
                       billing_detail.status                AS status,
                       billing_detail.date_of_service       AS dateOfService
                 FROM billing_detail
                WHERE patient_internal_id = %s
                AND billing_org_id IN ({f_str})
                ORDER BY date_of_service DESC""".format(
        f_str=f_str
    )
    bills = read_as_dict(cnx, query, (patient_id, tuple(org_ids)))
    return bills if bills else []


def get_common_org_id(cnx, patient_id, provider_id):
    """
    Returns list of common org ids for the input patient and provider
    """
    pat_orgs = get_user_org_ids(cnx, "patient", internal_id=patient_id)
    prv_orgs = get_user_org_ids(cnx, "providers", internal_id=provider_id)
    common_org = set(pat_orgs).intersection(set(prv_orgs))
    if common_org:
        return list(common_org)
    return None


def get_billing_list(patient_id, provider_id):
    """
    Returns bill data for the selected patient and provider
    """
    query = """ SELECT remote_monitoring
    FROM providers
    WHERE internal_id = %s
    AND remote_monitoring = 'Y' """
    is_rm_enabled = read_query(cnx, query, (provider_id))
    if is_rm_enabled:
        orgs = get_common_org_id(cnx, patient_id, provider_id)
        if not orgs:
            records = find_billing_by_patient_and_provider(cnx, patient_id, provider_id)
        else:
            records = find_billing_by_patient_and_org(cnx, patient_id, orgs)
    else:
        records = find_billing_by_patient_and_provider(cnx, patient_id, provider_id)
    response = []
    for rec in records:
        try:
            if rec["status"] == "Approve" or rec["providerId"] == provider_id:
                rec["charges"] = json.loads(rec["charges"])
                rec["diagnoses"] = json.loads(rec["diagnoses"])
                rec["dateOfService"] = rec["dateOfService"].strftime("%m-%d-%Y")
                response.append(rec)
        except GeneralException as e:
            logger.exception(e)
    return response


def delete_billing(billing_id):
    """
    This function:
    1. Searches for bill data in Draft bills for the given billing id
    2. If bill exists then the bill is deleted from DB
    3. If bill doesnt exist or isnt in deaft status then
       error message is sent to user
    """
    query = """ SELECT id FROM billing_detail WHERE id = %s AND status = 'Draft' """
    bill = read_as_dict(cnx, query, (billing_id))
    if bill:
        bill_id = bill[0]["id"]
        try:
            with cnx.cursor() as cursor:
                cursor.execute("DELETE FROM billing_detail WHERE id = %s", (bill_id))
                cnx.commit()
            logger.info("billing id " + str(billing_id) + " deleted")
            return "Billing Deleted successfully"
        except pymysql.MySQLError as err:
            logger.error(err)
    else:
        logging.info(
            "billing id " + str(billing_id) + " not found or not in Draft status"
        )
        return "Error While Deleting Billing"


def get_patient_diagnoses(cnx, patient_id):
    """
    Get list of diagnosis codes assigned to a patient
    """
    query = """ SELECT assigned_code FROM code_assigned WHERE patient_internal_id =%s"""
    codes = read_query(cnx, query, (patient_id))
    return [row[0] for row in codes]


def save_diagnoses(cnx, diagnose_code, patient_internal_id):
    """
    This function Adds/Updates diagnosis codes assigned to a patient
    """
    logger.info("patient:" + str(patient_internal_id) + " diagnoses:" + diagnose_code)
    diagnose_code = json.loads(diagnose_code)
    exist_codes = get_patient_diagnoses(cnx, patient_internal_id)
    for diag_code in diagnose_code:
        try:
            code = diag_code["code"]
            if code not in exist_codes:
                with cnx.cursor() as cursor:
                    cursor.execute(
                        """ INSERT into code_assigned (assigned_code, patient_internal_id)
                                    VALUES (%s, %s)""",
                        (code, patient_internal_id),
                    )
                    cnx.commit()
        except GeneralException as e:
            logger.error(e)


def parse(record_dict):
    """
    This function converts input dict to required dict format for billing
    """
    try:
        record = {}
        if "id" in record_dict:
            record["id"] = record_dict["id"].strip('"')
        record["provider_internal_id"] = record_dict["providerId"].strip('"')
        record["date_of_service"] = datetime.strptime(
            record_dict["dateOfService"], "%m/%d/%Y %H:%M:%S"
        )
        record["patient_internal_id"] = record_dict["patientId"].strip('"')
        if "providerName" in record_dict:
            record["provider_name"] = record_dict["providerName"].strip('"')
        else:
            record["provider_name"] = None
        record["billing_diagnose_code"] = record_dict["diagnoses"]
        record["billing_charge_code"] = record_dict["charges"]
        record["patient_location"] = record_dict["patientLocation"].strip('"')
        record["provider_location"] = record_dict["providerLocation"].strip('"')
        record["total_duration_billed"] = record_dict["currentMonthContactTime"].strip(
            '"'
        )
        record["status"] = record_dict["status"].strip('"')
        return record
    except GeneralException as e:
        logger.exception(e)


def list_procedures(charges, counter, record, diagnoses):
    """
    Returns Procedures Data based on input billing record,
    diagnoses, priority, charges and diagnoses
    """
    procedures = []
    for charge in charges:
        proc = {}
        proc["cpt_code_name"] = charge["code"]
        proc["quantity"] = 1
        proc["priority"] = counter
        proc["service_date_from"] = str(record["date_of_service"])[0:10]
        proc["service_date_to"] = proc["service_date_from"]
        d_count = 1
        icds = []
        for diagnose in diagnoses:
            icd = {}
            icd["priority"] = d_count
            icd["icd_code_name"] = diagnose["code"]
            d_count = d_count + 1
            icds.append(icd)
        proc["icds"] = icds
        counter = counter + 1
        procedures.append(proc)
    return procedures


def send_to_cds(cnx, record):
    """
    This function gets patient and provider data from billing record
    and adds billing data in CDS
    """
    # get ref_uid for patient.
    patient = find_user_by_internal_id(cnx, record["patient_internal_id"], "patient")
    if patient and patient["ref_uid"]:
        pat_ref_uid = patient["ref_uid"]
    else:
        logger.error(
            "patient or ref_uid not found:" + str(record["patient_internal_id"])
        )
    logging.info(
        "patient internal_id: {}, cds ref_id: {}".format(
            record["patient_internal_id"], pat_ref_uid
        )
    )
    # get provider_ref_uid. using provider location's zip code to look up the cds location id.
    provider = find_user_by_internal_id(
        cnx, record["provider_internal_id"], "providers"
    )
    if provider and provider["ref_uid"]:
        prv_ref_uid = provider["ref_uid"]
    else:
        logger.error(
            "provider or ref_uid not found:" + str(record["provider_internal_id"])
        )
        return 0
    profile_data = get_phi_data(provider["external_id"])
    zip_code = profile_data.get("address_zip")
    query = """ SELECT ref_id FROM location WHERE zip = %s"""
    ref_id = read_as_dict(cnx, query, (zip_code))
    if ref_id and ref_id[0]:
        location_id = ref_id[0]
    else:
        location_id = "26"
    logger.info(
        "provider location. zip: {}, cds location_id: {}".format(zip_code, location_id)
    )
    diagnoses = json.loads(record["billing_diagnose_code"])
    charges = json.loads(record["billing_charge_code"])
    counter = 1
    procedures = list_procedures(
        charges=charges,
        counter=counter,
        diagnoses=diagnoses,
        record=record,
    )
    # build the request now
    cds_request = {}
    cds_request["service_provider_id"] = prv_ref_uid
    cds_request["service_location_id"] = location_id
    cds_request["patient_id"] = pat_ref_uid
    cds_request["procedures"] = procedures
    cds_request["external_id_1"] = str(record["id"])
    cds_request["external_id_2"] = str(record["provider_internal_id"])
    logger.info("Logging CDS Request")
    logger.info(json.dumps(cds_request))

    # call cds API
    if token_cds is None:
        logging.error("CDS_TOKEN is missing from app.yaml")
        return 0
    serverUrl = host_cds + "encounters"
    tokenString = "Bearer " + token_cds
    newHeaders = {
        "Content-type": "application/json",
        "Accept": "text/plain",
        "Authorization": tokenString,
    }
    logger.info("sending billing info to url: {}".format(serverUrl))
    try:
        response = requests.post(
            serverUrl, data=json.dumps(cds_request), headers=newHeaders, timeout=5
        )
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    responseJson = response.json()
    logger.info("Logging CDS Response")
    logger.info(responseJson)
    logger.info(
        "Status code: {}, response: {}".format(
            response.status_code, str(response.json())
        )
    )
    cds_id = responseJson["id"]
    logging.info(
        "for internal billing id %s: cds billing id assigned %s, processed: %s, status_id: %s"
        % (
            record["id"],
            responseJson["id"],
            responseJson["processed"],
            responseJson["status_id"],
        )
    )
    return cds_id


def update_ref_uid(cnx, cds_id, billing_id):
    """
    This function updates ref_uid field for row with billing id
    to the CDS id returned
    """
    query = """ UPDATE billing_detail SET ref_uid = %s WHERE id = %s """
    with cnx.cursor() as cursor:
        cursor.execute(query, (cds_id, billing_id))
        cnx.commit()


def post_billing(record_dict):
    """
    This function:
    1. Adds Billing data for user based on input bill data
    2. Creates CDS record if the bill status is Approved
    """
    try:
        rec = parse(record_dict)
        query = """ SELECT billing_permission FROM providers where internal_id = %s """
        bill_permission = read_as_dict(cnx, query, (rec["provider_internal_id"]))
        if bill_permission and bill_permission[0]["billing_permission"] != "Y":
            logger.warnings("post failed. no billing permission for provider")
            return None
        date_created = datetime.now()
        date_updated = date_created
        org_id = get_common_org_id(
            cnx, rec["patient_internal_id"], rec["provider_internal_id"]
        )
        org_id = org_id[0] if org_id else 0
        ref_uid = None
        save_diagnoses(cnx, rec["billing_diagnose_code"], rec["patient_internal_id"])
        insert_billing = """
        INSERT INTO billing_detail (date_of_service, patient_internal_id, provider_internal_id,
        provider_name, billing_org_id, billing_diagnose_code, billing_charge_code,
        patient_location, provider_location, total_duration_billed,
        date_created, date_updated, status, ref_uid)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) """
        params = (
            rec["date_of_service"],
            rec["patient_internal_id"],
            rec["provider_internal_id"],
            rec["provider_name"],
            org_id,
            rec["billing_diagnose_code"],
            rec["billing_charge_code"],
            rec["patient_location"],
            rec["provider_location"],
            rec["total_duration_billed"],
            date_created,
            date_updated,
            rec["status"],
            ref_uid,
        )
        with cnx.cursor() as cursor:
            cursor.execute(insert_billing, params)
            billing_id = cursor.lastrowid
            cnx.commit()
        rec["id"] = billing_id
        if rec["status"] == "Approve":
            cds_id = send_to_cds(cnx, rec)
            update_ref_uid(cnx, cds_id, billing_id)
        return "Billing Added successfully"
    except GeneralException as e:
        logger.error(e)


def update_billing(billing_id, record_dict):
    """
    This function:
    1. Updates Billing data for user based on input bill data and bill id
    2. Creates CDS record if the bill status is Approved
    """
    try:
        rec = parse(record_dict)
        rec["id"] = billing_id
        query = """ SELECT billing_permission FROM providers where internal_id = %s """
        bill_permission = read_as_dict(cnx, query, (rec["provider_internal_id"]))
        if bill_permission and bill_permission[0]["billing_permission"] != "Y":
            logger.warnings("post failed. no billing permission for provider")
            return None
        update_bill = """ UPDATE billing_detail SET date_of_service=%s, patient_internal_id=%s, provider_internal_id=%s,
                                                     provider_name=%s, billing_diagnose_code=%s, billing_charge_code=%s,
                                                     patient_location=%s, provider_location=%s, total_duration_billed=%s,
                                                     date_updated=%s, status=%s
                          WHERE id = %s
                          """
        params = (
            rec["date_of_service"],
            rec["patient_internal_id"],
            rec["provider_internal_id"],
            rec["provider_name"],
            rec["billing_diagnose_code"],
            rec["billing_charge_code"],
            rec["patient_location"],
            rec["provider_location"],
            rec["total_duration_billed"],
            datetime.now(),
            rec["status"],
            billing_id,
        )
        if bill_permission:
            with cnx.cursor() as cursor:
                cursor.execute(update_bill, params)
                cnx.commit()
            save_diagnoses(
                cnx, rec["billing_diagnose_code"], rec["billing_charge_code"]
            )
            if rec["status"] == "Approve":
                cds_id = send_to_cds(cnx, rec)
                rec["ref_uid"] = cds_id
                update_ref_uid(cnx, cds_id, billing_id)
            cnx.commit()
            return rec
        else:
            return None
    except GeneralException as e:
        logger.error(e)


def lambda_handler(event, context):
    """
    Handler Function
    """
    if event["httpMethod"] == "GET":
        patient_id = event["pathParameters"].get("patient_id")
        provider_id = event["pathParameters"].get("provider_id")
        result = get_billing_list(patient_id, provider_id)
    elif event["httpMethod"] == "DELETE":
        billing_id = event["pathParameters"].get("billing_id")
        result = delete_billing(billing_id)
    elif event["httpMethod"] == "POST":
        form_data = json.loads(event["body"])
        result = post_billing(form_data)
    elif event["httpMethod"] == "PUT":
        form_data = json.loads(event["body"])
        billing_id = event["pathParameters"].get("billing_id")
        result = update_billing(billing_id, form_data)
    return {
        "statusCode": 200,
        "body": json.dumps(result, default=str),
        "headers": get_headers(),
    }
