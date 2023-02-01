import json
import logging
from datetime import datetime, timedelta

import boto3
from custom_exception import GeneralException
from shared import get_db_connect, get_headers, get_phi_data, read_as_dict, utc_to_cst
from sqls.remote_monitoring import (
    GET_BILLING_DATE_OF_SERVICE,
    GET_BILLING_DETAIL,
    GET_CALL_DURATION,
    GET_CONNECTED_PROVIDERS_WITH_PATIENT,
    GET_DEVICE_DETAILS,
    GET_DEVICE_READING_COUNT,
    GET_PHYSICIAN_WITH_RM_ENABLED,
    GET_PROVIDER_NETWORK,
)

logger = logging.getLogger(__name__)
dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()


def get_physician_with_rm_enabled(cnx, org_id, provider_id=None):
    """Get Physician with remote monitoring enabled"""
    query = GET_PHYSICIAN_WITH_RM_ENABLED
    if provider_id:
        query = query + " AND providers.internal_id = %(provider_id)s"
    return read_as_dict(
        cnx, query, {"org_id": org_id, "provider_id": provider_id}, fetchone=True
    )


def get_device_details(cnx, patient_id):
    """Get the device details"""
    device_pairing = read_as_dict(cnx, GET_DEVICE_DETAILS, {"patient_id": patient_id})
    result = [
        {"imei": d["imei"], "start_date": d["start_date"], "end_date": d["end_date"]}
        for d in device_pairing
    ]
    return result


def get_connected_prv_with_patient(cnx, patient_id, org_id):
    """
    Returns list of all providers connected to the patient in the same org
    """
    return read_as_dict(
        cnx,
        GET_CONNECTED_PROVIDERS_WITH_PATIENT,
        {"org_id": org_id, "patient_id": patient_id},
    )


def get_billing_date_of_service(cnx, patient_id):
    """Get Billing Date of Service"""
    params = {
        "code_nine_four": None,
        "patient_id": patient_id,
        "start_dt": None,
        "end_dt": None,
    }
    result = read_as_dict(cnx, GET_BILLING_DATE_OF_SERVICE, params)
    try:
        for record in result:
            billing_charge_code_list = eval(str(record["billing_charge_code"]))
            logger.info(billing_charge_code_list)
            if "99453" in [obj["code"] for obj in billing_charge_code_list]:
                return record["date_of_service"], record["provider_name"]
            return None, None
        return None, None
    except NameError as err:
        logger.error(err)
        return None, None


def get_date_of_service_code_nine_four(cnx, patient_internal_id, start_dt, end_dt):
    """Get Date of service code 99454"""
    params = {
        "start_dt": start_dt,
        "code_nine_four": True,
        "end_dt": end_dt,
        "patient_id": patient_internal_id,
    }
    result = read_as_dict(cnx, GET_BILLING_DATE_OF_SERVICE, params)
    for record in result:
        billing_charge_code_list = json.loads(record["billing_charge_code"])
        if "99454" in [obj["code"] for obj in billing_charge_code_list]:
            return record["date_of_service"]
    return None


def get_call_duration(cnx, patient_id, provider_ids, start_dt, end_dt):
    """Get Call duration"""
    call_records = {}
    params = {
        "patient_id": patient_id,
        "prv_ids": tuple(provider_ids),
        "start_dt": start_dt,
        "end_dt": end_dt,
    }
    result = read_as_dict(cnx, GET_CALL_DURATION, params)
    for call in result:
        st_timestamp = utc_to_cst(call["start_timestamp"])
        month = st_timestamp.month
        if month in call_records:
            call_records[month] += call["duration"]
        else:
            call_records[month] = call["duration"]
    logger.info(call_records)
    return call_records


def get_billing_detail(cnx, patient_id, start_dt, end_dt):
    """Get Billing Details"""
    params = {"patient_id": patient_id, "start_dt": start_dt, "end_dt": end_dt}
    result = read_as_dict(cnx, GET_BILLING_DETAIL, params)
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
    except GeneralException as err:
        logger.info(err)
    return final_result


def get_device_reading_within_timestamp(cnx, patient_id, start_dt, end_dt):
    """Get Device Reading Count"""
    params = {
        "patient_id": patient_id,
        "start_dt": str(start_dt.date()),
        "end_dt": str(end_dt.date()),
    }
    result = read_as_dict(cnx, GET_DEVICE_READING_COUNT, params, fetchone=True)
    return result["reading_count"]


def get_days_of_records(cnx, patient_internal_id, start_date, end_date, device):
    """Get days of device Recordings"""
    # start_date and end_date
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
            record_["start_date"] = date_of_pairing
            date_of_pairing += timedelta(days=30)
            record_["end_date"] = date_of_pairing
            if start_date1.date() <= date_of_pairing.date():
                date_of_service_code_nine_four = get_date_of_service_code_nine_four(
                    cnx, patient_internal_id, record_["start_date"], record_["end_date"]
                )
                if date_of_service_code_nine_four:
                    record_["start_date"] = date_of_service_code_nine_four
                    record_["end_date"] = date_of_service_code_nine_four + timedelta(
                        days=30
                    )
                    date_of_pairing = record_["end_date"]
                date_of_pairing += timedelta(days=1)
                number_of_days = get_device_reading_within_timestamp(
                    cnx, patient_internal_id, record_["start_date"], record_["end_date"]
                )
                record_["number_of_days"] = number_of_days
                final_result.append(record_)
            if date_of_pairing.date() > end_date1.date():
                break
    else:
        # case 2: when device pairing date is in between three months period
        while True:
            record_ = {}
            date_of_pairing += timedelta(days=1)
            record_["start_date"] = date_of_pairing
            date_of_pairing += timedelta(days=30)
            record_["end_date"] = date_of_pairing
            number_of_days = get_device_reading_within_timestamp(
                cnx, patient_internal_id, record_["start_date"], record_["end_date"]
            )
            record_["number_of_days"] = number_of_days
            final_result.append(record_)
            end_date1 = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
            if date_of_pairing.date() > end_date1.date():
                break

    return final_result


def get_patients_based_on_provider_id(
    cnx, provider_id, start_dt, end_dt, patient_data, org_id
):
    """Get Detailed list of patients"""
    result = []
    patients_in_network = read_as_dict(
        cnx, GET_PROVIDER_NETWORK, {"provider_id": provider_id}
    )
    for pat in patients_in_network:
        record = {}
        device_details = get_device_details(cnx, pat["internal_id"])
        if len(device_details) == 0 or pat["internal_id"] in patient_data:
            continue
        phi_data = get_phi_data(pat["external_id"], dynamodb)
        connected_prvs = get_connected_prv_with_patient(cnx, pat["id"], org_id)
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
            cnx, pat["internal_id"]
        )
        record["date_of_service_99453"] = date_of_service_99453
        record["creator_of_99453"] = creator_of_99453
        record["remote_monitoring"] = pat["remote_monitoring"]
        record["paired_device_details"] = device_details
        record["call_records"] = get_call_duration(
            cnx, pat["internal_id"], rm_prv_ids, start_dt, end_dt
        )
        record["billing_details"] = get_billing_detail(
            cnx, pat["internal_id"], start_dt, end_dt
        )
        record["days_recording"] = []
        for device in device_details:
            record["days_recording"].extend(
                get_days_of_records(cnx, pat["internal_id"], start_dt, end_dt, device)
            )
            break
        if record:
            result.append(record)
            patient_data[pat["internal_id"]] = record

    return result


def get_remote_monitoring_report(cnx, org_id, start_date, end_date):
    """Get Remote monitoring report for all"""
    result = []
    patient_data = {}
    all_remote_enabled_providers = get_physician_with_rm_enabled(cnx, org_id)
    for record in all_remote_enabled_providers:
        patient_details = get_patients_based_on_provider_id(
            cnx, record["internal_id"], start_date, end_date, patient_data, org_id
        )
        for patient_detail in patient_details:
            result.append(patient_detail)
    result = sorted(result, key=lambda x: x["patient_last_name"])
    return {"patient_details": result}


def get_remote_monitoring_report_for_single_provider(
    cnx, org_id, provider_id, start_date, end_date
):
    """
    Returns remote monitoring report for all patients of the selected provider
    """
    result = []
    provider = get_physician_with_rm_enabled(cnx, org_id, provider_id)
    patient_data = {}
    if not provider:
        return []
    record_ = {
        "provider_name": provider["name"],
        "provider_id": provider["internal_id"],
        "patient_details": get_patients_based_on_provider_id(
            cnx, provider["internal_id"], start_date, end_date, patient_data, org_id
        ),
    }
    result.append(record_)
    return result


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    print(event)
    auth_user = event["requestContext"].get("authorizer")
    query_string = (
        event["queryStringParameters"] if event.get("queryStringParameters") else {}
    )
    start_date = query_string.get("start_date", None)
    end_date = query_string.get("end_date", None)
    if start_date and end_date:
        date_format = "%Y-%m-%d %H:%M:%S"
        try:
            bool(datetime.strptime(start_date, date_format))
            bool(datetime.strptime(end_date, date_format))
        except ValueError as err:
            logger.error(err)
            raise GeneralException("Invalid Date format")
    else:
        curr_dt = datetime.now()
        end_date = curr_dt.strftime("%Y-%m-%d %H:%M:%S")
        diff_dt = curr_dt - timedelta(days=90)
        start_date = diff_dt.strftime("%Y-%m-%d %H:%M:%S")
    if event["pathParameters"]:
        prv_id = event["pathParameters"].get("prv_id")
        result = get_remote_monitoring_report_for_single_provider(
            connection, auth_user["userOrg"], prv_id, start_date, end_date
        )
    else:
        result = get_remote_monitoring_report(
            connection, auth_user["userOrg"], start_date, end_date
        )
    return {
        "statusCode": 200,
        "body": json.dumps(result, default=str),
        "headers": get_headers(),
    }
