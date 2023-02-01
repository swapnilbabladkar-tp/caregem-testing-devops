import ast
import json
import logging
from datetime import datetime
from http import HTTPStatus
from typing import Tuple

import pymysql
from shared import (
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_user_org_ids,
    read_as_dict,
)
from sqls.call import (
    CALL_BASE_QUERY,
    DRAFT_CALL_RECORD_BELONGS_TO_PROVIDER,
    INSERT_CALL_RECORDS,
    REMOTE_MONITORING_PROVIDER,
    SOFT_DELETE_DRAFT_CALL_RECORD,
    UPDATE_CALL_RECORDS,
    UPDATE_MANUAL_CALL_RECORDS,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_common_org_id(cnx, patient_id, provider_id):
    """
    Get the common org id.
    :params patient_id, provider_id, cnx obj
    :Return common org_ids
    """
    pat_orgs = get_user_org_ids(cnx, "patient", internal_id=patient_id)
    prv_orgs = get_user_org_ids(cnx, "providers", internal_id=provider_id)
    common_org = set(pat_orgs).intersection(set(prv_orgs))
    if common_org:
        return list(common_org)
    return None


def consider_org_id(cnx, patient_id, provider_id):
    """
    This Function:
    1. Checks if remote monitoring is emabled for provider
    2. Gets common org ids for patient and provider
    3. returns first common org id if provider has
       remote monitoring enabled and common org ids are present
    4. returns 0 if above condition is false
    """
    is_prv_rm = read_as_dict(
        cnx, REMOTE_MONITORING_PROVIDER, {"provider_id": provider_id}
    )
    org_id = get_common_org_id(cnx, patient_id, provider_id)
    logger.info("Common org Id is %s ", org_id)
    logger.info("Provider Remote Monitoring Enabled %s", is_prv_rm)
    if is_prv_rm and org_id:
        return org_id[0]
    return 0


def get_call_base_query(cnx, patient_id, org_id=None):
    """
    Get Call Base Query
    :params patient_id, org_id
    :return call records
    """
    n_org_id = True if org_id else None
    params = {
        "org_ids": org_id,
        "patient_id": patient_id,
        "n_org_id": n_org_id,
        "status": tuple(["DRAFT", "COMPLETED"]),
    }
    call_records = read_as_dict(cnx, CALL_BASE_QUERY, params)
    return call_records


def get_call_logs(cnx, patient_id, org_id):
    """
    Get Call Logs
    :params patient_id, org_id
    :return dict call logs
    """
    call_logs = get_call_base_query(cnx, patient_id, org_id)
    final_set = []
    for call in call_logs:
        item = {
            "call_duration": int(call.get("duration", "0") or 0),
            "status": call.get("status"),
            "prv_name": call.get("provider_name"),
            "provider_internal_id": call.get("provider_internal_id"),
            "patient_internal_id": call.get("patient_internal_id"),
            "id": call["id"],
            "date_p": (
                call["start_timestamp"].strftime("%m-%d-%Y %I:%M %p")
                if call.get("start_timestamp")
                else ""
            ),
            "call_type": call.get("type_of_call"),
        }
        final_set.append(item)
    return final_set


def get_call_records(cnx, patient_id, org_id):
    """
    Get Call Records
    :params patient_id, org_id
    :return call records
    """
    call_records = get_call_base_query(cnx, patient_id, org_id)
    final_set = []
    for call in call_records:
        item = {
            "call_duration": int(call.get("duration", "0") or 0),
            "id": call["id"],
            "status": call.get("status"),
            "call_type": call.get("type_of_call"),
            "prv_name": call.get("provider_name"),
            "provider_internal_id": call.get("provider_internal_id"),
            "patient_internal_id": call.get("patient_internal_id"),
            "date_p": (
                call["start_timestamp"].strftime("%B %d, %Y %I:%M %p")
                if call.get("start_timestamp")
                else ""
            ),
        }
        notes = call.get("notes")
        if not notes or notes == "[]":
            item["desc"] = ""
            item["notes"] = ""
        else:
            notes = ast.literal_eval(notes.replace("\n", ""))
            item["desc"] = "<br>".join(
                [d.get("desc") for d in notes if d.get("id") != "999"]
            )
            item["notes"] = "<br>".join(
                [n.get("desc") for n in notes if n.get("id") == "999"]
            )
        final_set.append(item)
    return final_set


def add_call_records(cnx, data):
    """
    Insert Call Record based on input data
    """
    org_id = get_common_org_id(cnx, data["patient_id"], data["provider_id"])
    org_id = 0 if not org_id else org_id[0]
    params = {
        "patient_internal_id": data["patient_id"],
        "provider_internal_id": data["provider_id"],
        "start_timestamp": datetime.strptime(data["callDateTime"], "%m-%d-%Y %H:%M"),
        "duration": data["callLength"],
        "status": data["status"],
        "type_of_call": data["typeOfCall"],
        "org_id": org_id,
        "notes": json.dumps(data["notes"]),
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_CALL_RECORDS, params)
            cnx.commit()
            return "success"
    except pymysql.MySQLError as err:
        logger.error(err)


def update_call_records(cnx, data, call_id):
    """
    Update call record data based on
    type of call in the input call record data
    """
    if data["typeOfCall"] == "Manual":
        params = {
            "start_timestamp": datetime.strptime(
                data["callDateTime"], "%m-%d-%Y %H:%M"
            ),
            "duration": data["callLength"],
            "status": data["status"],
            "notes": json.dumps(data["notes"]),
            "id": call_id,
        }
    else:
        params = {
            "notes": json.dumps(data["notes"]),
            "status": data["status"],
            "id": call_id,
        }
    try:
        with cnx.cursor() as cursor:
            query = (
                UPDATE_MANUAL_CALL_RECORDS
                if data["typeOfCall"] == "Manual"
                else UPDATE_CALL_RECORDS
            )
            cursor.execute(query, params)
            cnx.commit()
            return "updated successfully"
    except pymysql.MySQLError as err:
        logger.error(err)


def delete_call_record(
    cnx, call_id: str, provider_external_id: str
) -> Tuple[HTTPStatus, str]:
    """
    This function:
    1. Gets provider data
    2. Checks if provider is the owner of the call record and
       the call record is in draft status
    3. Changes call record status to DELETED if above is true
    """
    provider = find_user_by_external_id(
        cnx=cnx, external_id=provider_external_id, role="providers"
    )

    # check if the `provider` is the owner of the `call_id` and the status of `call_id` is `Draft`
    params = {"call_id": call_id, "provider_internal_id": provider.get("internal_id")}
    draft_call_record = read_as_dict(
        connection=cnx,
        query=DRAFT_CALL_RECORD_BELONGS_TO_PROVIDER,
        params=params,
        fetchone=True,
    )
    if not draft_call_record:
        return HTTPStatus.NOT_FOUND, "Invalid call_id."

    # Update the status of call_id to `DELETED`
    try:
        with cnx.cursor() as cursor:
            cursor.execute(SOFT_DELETE_DRAFT_CALL_RECORD, {"call_id": call_id})
            cnx.commit()
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, "Delete operation failed."

    return HTTPStatus.OK, "Call Record deleted successfully."


def lambda_handler(event, context):
    """
    Handler Function.
    """
    status_code = None

    auth_user = event["requestContext"].get("authorizer")
    if event["pathParameters"]:
        patient_id = event["pathParameters"].get("patient_id")
    if event["httpMethod"] == "GET":
        if auth_user.get("userOrg"):
            org_id = [auth_user["userOrg"]]
        else:
            user = find_user_by_external_id(
                connection, auth_user["userSub"], "providers"
            )
            org_id = consider_org_id(connection, patient_id, user["internal_id"])
        if not org_id:
            result = []
        elif "call_logs" in event["path"].split("/"):
            result = get_call_logs(connection, patient_id, org_id)
        elif "call_records" in event["path"].split("/"):
            result = get_call_records(connection, patient_id, org_id)
    elif event["httpMethod"] == "POST":
        form_data = json.loads(event["body"])
        result = add_call_records(connection, form_data)
    elif event["httpMethod"] == "PUT":
        call_id = event["pathParameters"].get("call_id")
        form_data = json.loads(event["body"])
        result = update_call_records(connection, form_data, call_id)
    elif event["httpMethod"] == "DELETE":
        call_id = event["pathParameters"].get("call_id")
        status_code, result = delete_call_record(
            cnx=connection, call_id=call_id, provider_external_id=auth_user["userSub"]
        )
    return {
        "statusCode": 200 if not status_code else status_code.value,
        # TODO: return status code from other helper methods
        "body": json.dumps(result),
        "headers": get_headers(),
    }
