import json
import logging
from datetime import datetime, timedelta

import boto3
from custom_exception import GeneralException
from shared import (
    get_db_connect,
    get_headers,
    get_logged_in_user,
    get_phi_data,
    read_as_dict,
    utc_to_cst,
)

cnx = get_db_connect()
logger = logging.getLogger(__name__)
dynamodb = boto3.resource("dynamodb")


def get_physician_with_rm_enabled(org_id, internal_id=None):
    """
    Returns list of providers who have remote monitoring set as enabled
    """
    query = """ SELECT providers.id,
                       providers.username,
                       providers.activated,
                       providers.name,
                       providers.internal_id,
                       providers.`role`,
                       providers.`group`,
                       providers.specialty,
                       providers.remote_monitoring,
                       providers.billing_permission
                FROM   providers
                JOIN   provider_org
                ON     providers.id = provider_org.providers_id
                WHERE  provider_org.organizations_id = %s
                AND    providers.`role` = 'physician'
                AND    providers.remote_monitoring = 'Y'
            """
    if internal_id:
        query = query + " AND providers.internal_id = %s"
        result = read_as_dict(cnx, query, (org_id, internal_id))
    else:
        result = read_as_dict(cnx, query, (org_id))
    return result


def get_device_details(internal_id):
    """
    Returns the device_pairing details for a patient
    """
    query = """ SELECT * FROM device_pairing WHERE patient_internal_id =%s"""
    device_pairing = read_as_dict(cnx, query, (internal_id))
    result = [
        {"imei": d["imei"], "start_date": d["start_date"], "end_date": d["end_date"]}
        for d in device_pairing
    ]
    return result


def get_connected_prv_with_patient(patient_id, org_id):
    """
    Returns the list of users in the network of the input patient id in the same org
    """
    query = """ SELECT providers.id,
                       providers.username,
                       providers.activated,
                       providers.name,
                       providers.internal_id,
                       providers.`role`,
                       providers.`group`,
                       providers.specialty,
                       providers.remote_monitoring,
                       providers.billing_permission
                FROM   providers
                       join networks
                         ON providers.internal_id = networks.user_internal_id
                       join provider_org
                         ON providers.id = provider_org.providers_id
                WHERE  networks._patient_id = %s
                       AND provider_org.organizations_id = %s """
    return read_as_dict(cnx, query, (patient_id, org_id))


def get_billing_date_of_service(patient_id):
    """
    Returns date of service and provider name of "approved" billing details
    for the input patient id
    """
    query = """ SELECT billing_charge_code,
                       date_of_service,
                       provider_name
                FROM   billing_detail
                WHERE  billing_detail.patient_internal_id = %s
                       AND billing_detail.`status` = 'Approve'
                ORDER  BY billing_detail.date_of_service DESC
            """
    result = read_as_dict(cnx, query, (patient_id))
    try:
        for record in result:
            billing_charge_code_list = json.loads((str(record["billing_charge_code"])))
            if "99453" in [obj["code"] for obj in billing_charge_code_list]:
                return record["date_of_service"], record["provider_name"]
            return None, None
        return None, None
    except NameError as e:
        print(patient_id)
        print(e)
        return None, None


def get_duration_between_date(pat_int_id, prv_int_ids, start_dt, end_dt):
    """
    Returns dict with the total call duration for each month between
    the input start and end date for the selected patient and providers
    """
    f_str = ",".join(["%s"] * len(prv_int_ids))
    call_records = {}
    query = """ SELECT call_logs.id,
                       call_logs.start_timestamp,
                       call_logs.duration
                FROM   call_logs
                WHERE  call_logs.patient_internal_id = %s
                       AND call_logs.provider_internal_id IN ({f_str})
                       AND call_logs.start_timestamp >= %s
                       AND call_logs.start_timestamp <= %s
            """.format(
        f_str=f_str
    )
    result = read_as_dict(
        cnx, query, ((pat_int_id,) + tuple(prv_int_ids) + (start_dt, end_dt))
    )
    for call in result:
        st_timestamp = utc_to_cst(call["start_timestamp"])
        month = st_timestamp.month
        if month in call_records:
            call_records[month] += call["duration"]
        else:
            call_records[month] = call["duration"]
    logger.info(call_records)
    return call_records


def get_billing_detail(pat_int_id, start_dt, end_dt):
    """
    Returns billing details for the selected patient in the input date range
    """
    query = """ SELECT billing_charge_code,
                       DATE_FORMAT(date_of_service, '%%a, %%d %%b %%Y %%T') AS date_of_service,
                       provider_name,
                       billing_detail.`status`
                FROM   billing_detail
                WHERE  billing_detail.patient_internal_id = %s
                       AND billing_detail.date_of_service >= %s
                       AND billing_detail.date_of_service <= %s
                       AND billing_detail.`status` = 'Approve'
            """
    result = read_as_dict(cnx, query, (pat_int_id, start_dt, end_dt))
    final_result = []
    try:
        for record in result:
            billing_charge_code_list = json.loads(str(record["billing_charge_code"]))
            billing_charge_code_ids = [
                {
                    "billing_charge_code": obj["code"],
                    "date_of_service": record["date_of_service"],
                    "provider_name": record["provider_name"],
                }
                for obj in billing_charge_code_list
            ]
            final_result.extend(billing_charge_code_ids)
    except GeneralException as e:
        print(e, str(pat_int_id))
    return final_result


def get_device_reading_within_timestamp(pat_int_id, start_dt, end_dt):
    """
    Returns count of distinct readings reported between the input time range
    """
    query = """ SELECT count(distinct(reading_date))
                    FROM device_pairing_view WHERE
                    reading_date >= %s AND reading_date <= %s AND
                    patient_internal_id= %s """
    record = (str(start_dt.date()), str(end_dt.date()), pat_int_id)
    with cnx.cursor() as cursor:
        cursor.execute(query, record)
        result = cursor.fetchone()
        if result:
            return result[0]
        return None


def get_days_of_records(
    patient_internal_id, start_date, end_date, device
):  # start_date and end_date
    """
    Returns device pairing records for the selected patient for the given time range
    for each month with the number of readings reported for the month
    Format:
    list of {
        "start_date": <start date>,
        "end_date": <end date>,
        "number_of_days": <number of days>
    }
    """
    final_result = []
    device_pairing = device["start_date"]
    if device_pairing is None:
        return []
    # case 1: To handle date when device pairing date is before three months
    date_of_pairing = device_pairing
    start_date1 = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
    end_date1 = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
    if start_date1 > date_of_pairing:
        while True:
            record_ = {}
            date_of_pairing += timedelta(days=1)
            record_["start_date"] = date_of_pairing
            date_of_pairing += timedelta(days=30)
            record_["end_date"] = date_of_pairing
            if start_date1.date() <= date_of_pairing.date():
                number_of_days = get_device_reading_within_timestamp(
                    patient_internal_id, record_["start_date"], record_["end_date"]
                )
                record_["number_of_days"] = number_of_days
                final_result.append(record_)
            end_date1 = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
            if date_of_pairing.date() > end_date1.date():
                break
    else:
        # case 2: when device pairing date is in between three month period
        while True:
            record_ = {}
            date_of_pairing += timedelta(days=1)
            record_["start_date"] = date_of_pairing
            date_of_pairing += timedelta(days=30)
            record_["end_date"] = date_of_pairing
            number_of_days = get_device_reading_within_timestamp(
                patient_internal_id, record_["start_date"], record_["end_date"]
            )
            record_["number_of_days"] = number_of_days
            final_result.append(record_)
            end_date1 = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
            if date_of_pairing.date() > end_date1.date():
                break

    return final_result


def get_patients_based_on_provider_id(
    internal_id, start_dt, end_dt, patient_data, org_id
):
    """
    Returns list of patients in the input user's network along with
    their device pairing details
    """
    result = []
    query = """SELECT patients.activated,
               patients.id,
               patients.external_id,
               patients.internal_id,
               patients.remote_monitoring
        FROM   patients
               INNER JOIN networks
                       ON patients.id = networks._patient_id
        WHERE  networks.user_internal_id = %s
               AND patients.remote_monitoring = 'Y'
            """
    patients_in_network = read_as_dict(cnx, query, (internal_id))
    for pat in patients_in_network:
        record = {}
        device_details = get_device_details(pat["internal_id"])
        if len(device_details) == 0 or pat["internal_id"] in patient_data:
            continue
        phi_data = get_phi_data(pat["external_id"], dynamodb)
        connected_prvs = get_connected_prv_with_patient(pat["id"], org_id)
        physician_names = [
            x["name"]
            for x in connected_prvs
            if x["remote_monitoring"] == "Y" and x["role"] == "physician"
        ]
        prvs_rm_enabled = filter(
            lambda k: k["remote_monitoring"] == "Y", connected_prvs
        )
        rm_prv_ids = [int(item["internal_id"]) for item in prvs_rm_enabled]
        record["all_provider_name"] = ",".join(physician_names)
        record["patient_name"] = phi_data["first_name"] + " " + phi_data["last_name"]
        record["patient_first_name"] = phi_data["first_name"]
        record["patient_last_name"] = phi_data["last_name"]
        record["patient_internal_id"] = pat["internal_id"]
        date_of_service_99453, creator_of_99453 = get_billing_date_of_service(
            pat["internal_id"]
        )
        record["date_of_service_99453"] = date_of_service_99453
        record["creator_of_99453"] = creator_of_99453
        record["remote_monitoring"] = pat["remote_monitoring"]
        record["paired_device_details"] = device_details
        record["call_records"] = get_duration_between_date(
            pat["internal_id"], rm_prv_ids, start_dt, end_dt
        )
        record["billing_details"] = get_billing_detail(
            pat["internal_id"], start_dt, end_dt
        )
        record["days_recording"] = []
        for device in device_details:
            record["days_recording"].extend(
                get_days_of_records(pat["internal_id"], start_dt, end_dt, device)
            )
            break
        if record:
            result.append(record)
            patient_data[pat["internal_id"]] = record

    return result


def get_remote_monitoring_report(org_id):
    """
    Returns remote monitoring report for all patients of all providers for a given org
    """
    result = []
    curr_dt = datetime.now()
    end_dt = curr_dt.strftime("%Y-%m-%d %H:%M:%S")
    diff_dt = curr_dt - timedelta(days=90)
    start_dt = diff_dt.strftime("%Y-%m-%d %H:%M:%S")

    patient_data = {}

    all_remote_enabled_providers = get_physician_with_rm_enabled(org_id)
    for record in all_remote_enabled_providers:
        patient_details = get_patients_based_on_provider_id(
            record["internal_id"], start_dt, end_dt, patient_data, org_id
        )
        for patient_detail in patient_details:
            result.append(patient_detail)
    result = sorted(result, key=lambda x: x["patient_last_name"])
    return {"patient_details": result}


def get_remote_monitoring_report_for_single_provider(org_id, provider_id):
    """
    Returns remote monitoring report for all patients of the selected provider
    """
    result = []
    curr_dt = datetime.now()
    end_dt = curr_dt.strftime("%Y-%m-%d %H:%M:%S")
    diff_dt = curr_dt - timedelta(days=90)
    start_dt = diff_dt.strftime("%Y-%m-%d %H:%M:%S")
    provider = get_physician_with_rm_enabled(org_id, provider_id)[0]
    patient_data = {}
    if provider is None:
        return []
    record_ = {}
    record_["provider_name"] = provider["name"]
    record_["provider_id"] = provider["internal_id"]
    record_["patient_details"] = get_patients_based_on_provider_id(
        provider["internal_id"], start_dt, end_dt, patient_data, org_id
    )
    result.append(record_)
    return result


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    auth_user = get_logged_in_user(event["headers"]["Authorization"])
    # auth_user = event["requestContext"].get("authorizer")
    if event["pathParameters"]:
        prv_id = event["pathParameters"].get("prv_id")
        result = get_remote_monitoring_report_for_single_provider(
            auth_user["userOrg"], prv_id
        )
    else:
        result = get_remote_monitoring_report(auth_user["userOrg"])
    return {
        "statusCode": 200,
        "body": json.dumps(result, default=str),
        "headers": get_headers(),
    }
