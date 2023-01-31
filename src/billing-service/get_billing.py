import json
import logging

from custom_exception import GeneralException
from shared import (
    get_db_connect,
    get_headers,
    get_user_org_ids,
    read_as_dict,
    read_query,
)

logger = logging.getLogger(__name__)

connection = get_db_connect()


def find_billing_by_patient_and_provider(cnx, patient_id, provider_id):
    """
    Returns all bills for the selected patient and provider
    """
    query = """ SELECT CAST(billing_detail.patient_internal_id AS CHAR)   AS patientId,
                       CAST(billing_detail.id AS CHAR)                    AS id,
                       CAST(billing_detail.provider_internal_id AS CHAR)  AS providerId,
                       billing_detail.provider_name         AS providerName,
                       billing_detail.billing_diagnose_code AS diagnoses,
                       billing_detail.billing_charge_code   AS charges,
                       billing_detail.patient_location      AS patientLocation,
                       billing_detail.provider_location     AS providerLocation,
                       CAST(billing_detail.total_duration_billed AS CHAR) AS currentMonthContactTime,
                       billing_detail.status                AS status
                FROM billing_detail
                WHERE patient_internal_id = %s
                AND provider_internal_id =%s
                ORDER BY date_of_service DESC """
    bills = read_as_dict(cnx, query, (patient_id, provider_id))
    return bills if bills else []


def find_billing_by_patient_and_org(cnx, patient_id, org_ids):
    """
    Returns all bills in the input orgs for the selected patient
    """
    f_str = ",".join(["%s"] * len(org_ids))
    query = """ SELECT CAST(billing_detail.patient_internal_id AS CHAR)  AS patientId,
                       CAST(billing_detail.id AS CHAR)                    AS id,
                       CAST(billing_detail.provider_internal_id AS CHAR) AS providerId,
                       billing_detail.provider_name         AS providerName,
                       billing_detail.billing_diagnose_code AS diagnoses,
                       billing_detail.billing_charge_code   AS charges,
                       billing_detail.patient_location      AS patientLocation,
                       billing_detail.provider_location     AS providerLocation,
                       CAST(billing_detail.total_duration_billed AS CHAR) AS currentMonthContactTime,
                       billing_detail.status                AS status,
                       billing_detail.date_of_service       AS dateOfService
                 FROM billing_detail
                WHERE patient_internal_id = %s
                AND billing_org_id IN ({f_str})
                ORDER BY date_of_service DESC """.format(
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


def get_billing(cnx, patient_id, provider_id):
    """
    Returns bill data for the selected patient and provider
    """
    query = """ SELECT remote_monitoring FROM providers WHERE internal_id = %s AND remote_monitoring = 'Y' """
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
                rec["charges"] = eval(rec["charges"])  # pylint: disable=W0123
                rec["diagnoses"] = eval(rec["diagnoses"])  # pylint: disable=W0123
                rec["dateOfService"] = rec["dateOfService"].strftime("%m-%d-%Y")
                response.append(rec)
        except GeneralException as e:
            logger.exception(e)
    return response


def get_last_billing(cnx, patient_id, provider_id):
    """
    This function returns latest approved bill
    for the selected patient and provider
    """
    records = get_billing(cnx, patient_id, provider_id)
    for rec in records:
        if rec["status"] == "Approve":
            return rec
    return {}


def lambda_handler(event, context):
    """
    The api will handle billing List
    """
    patient_id = event["pathParameters"].get("patient_id")
    provider_id = event["pathParameters"].get("provider_id")
    if "lastbilling" in event["path"].split("/"):
        result = get_last_billing(connection, patient_id, provider_id)
    else:
        result = get_billing(connection, patient_id, provider_id)
    return {
        "statusCode": 200,
        "body": json.dumps(result, default=str),
        "headers": get_headers(),
    }
