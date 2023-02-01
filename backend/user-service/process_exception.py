import json
import logging
from http import HTTPStatus

import pymysql
from crontask import get_sftp_client, process_hl7_fields
from patient_crud import create_patient, update_patient
from shared import (
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data,
    read_as_dict,
)
from sqls.user import GET_EXCEPTION_BY_ID, GET_USER_EXCEPTION, UPDATE_EXCEPTION_STATUS
from user_utils import get_user_exception, link_user_to_new_org
from username import get_user_name

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def fetch_exception(cnx, org_id):
    """List all the exceptions for a given org id"""
    exceptions = read_as_dict(cnx, GET_USER_EXCEPTION, {"org_id": org_id})
    response = {}
    if exceptions:
        sftp_client, directory = get_sftp_client()
        directory = directory + "/EXCEPTION/"
        sftp_client.chdir(directory)
        for item in exceptions:
            if (
                item["org_id"] != item["matching_org_id"]
                and item["matching_org_id"] == org_id
                and len(item["matching_fields"].split(",")) < 3
            ):
                continue
            if item["cds_or_s3_file_path"] not in response:
                response[item["cds_or_s3_file_path"]] = {}
                if item["ref_uid"] and item["ref_uid"] != "999":
                    remote_file = sftp_client.open(
                        item["cds_or_s3_file_path"], bufsize=32768
                    )
                    lines = remote_file.read().splitlines()
                    user_data = process_hl7_fields(lines)[1]
                    response[item["cds_or_s3_file_path"]]["user_data"] = user_data
                    response[item["cds_or_s3_file_path"]]["user_data"]["org_id"] = item[
                        "org_id"
                    ]
                    matching_data = get_phi_data(item["matching_external_id"])
                    matching_data["matching_org_id"] = item["matching_org_id"]
                    matching_data["exception_id"] = item["id"]
                    matching_data["status"] = item["status"]
                    matching_data["matching_fields"] = item["matching_fields"]
                    response[item["cds_or_s3_file_path"]]["matching_data"] = [
                        matching_data
                    ]
                else:
                    user_data = get_user_exception(item["cds_or_s3_file_path"])
                    response[item["cds_or_s3_file_path"]]["user_data"] = user_data
                    response[item["cds_or_s3_file_path"]]["user_data"]["org_id"] = item[
                        "org_id"
                    ]
                    matching_data = get_phi_data(item["matching_external_id"])
                    matching_data["matching_org_id"] = item["matching_org_id"]
                    matching_data["exception_id"] = item["id"]
                    matching_data["status"] = item["status"]
                    matching_data["matching_fields"] = item["matching_fields"]
                    response[item["cds_or_s3_file_path"]]["matching_data"] = [
                        matching_data
                    ]
            else:
                matching_data = get_phi_data(item["matching_external_id"])
                matching_data["matching_org_id"] = item["matching_org_id"]
                matching_data["org_id"] = item["org_id"]
                matching_data["matching_fields"] = item["matching_fields"]
                matching_data["exception_id"] = item["id"]
                matching_data["status"] = item["status"]
                response[item["cds_or_s3_file_path"]]["matching_data"].append(
                    matching_data
                )
        return HTTPStatus.OK, list(response.values())
    return HTTPStatus.OK, []


def update_exception_status(cnx, idn, status):
    """
    Update status value for input exception id
    """
    try:
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_EXCEPTION_STATUS, {"id": idn, "status": status})
            cnx.commit()
        return HTTPStatus.OK, f"Status updated to {status} for id {idn}"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, "Error while Updating Status"


def process_exceptions(cnx, form_data, org_id, idn, auth_user=None):
    """
    This function handles Actions on Generated Exception
    The actions create_new or uodate can be performed
    1. "create_new" creates a new user in the input org
    2. "update" updates an existing user's data and links user to the new org
       if the user's org isnt the same as the input org
    """
    status_code = HTTPStatus.BAD_REQUEST
    user_result = "Invalid API call"
    if form_data["msg_code"] == "add_new":
        form_data["username"] = get_user_name(
            form_data["first_name"], form_data["last_name"]
        )
        status_code, user_result = create_patient(cnx, form_data, org_id)
        update_exception_status(cnx, idn, "ARCHIVED")

    elif form_data["msg_code"] == "update":
        user_exception = read_as_dict(
            cnx, GET_EXCEPTION_BY_ID, {"id": idn}, fetchone=True
        )
        matching_external_id = user_exception["matching_external_id"]
        user = find_user_by_external_id(
            cnx, external_id=matching_external_id, role="patient"
        )
        if org_id != form_data["org_id"]:
            user_result = link_user_to_new_org(cnx, user, form_data["role"], org_id)
            logger.info(user_result)
        status_code, user_result = update_patient(
            cnx, user["id"], form_data, None, auth_user
        )
        update_exception_status(cnx, idn, "ARCHIVED")
    return status_code, user_result


def lambda_handler(event, context):
    """
    Org portal Patient Handler
    """
    auth_user = event["requestContext"].get("authorizer")
    identity = event["requestContext"].get("identity")
    auth_user["ipv4"] = identity.get("sourceIp", None)
    org_id = auth_user["userOrg"]
    auth_user.update(
        find_user_by_external_id(
            connection, auth_user["userSub"], auth_user["userRole"]
        )
    )
    if event["httpMethod"] == "GET":
        status_code, result = fetch_exception(connection, org_id)
    elif event["httpMethod"] == "PUT":
        if "status" in event["path"].split("/"):
            idn = event["pathParameters"].get("id")
            form_data = json.loads(event["body"])
            status = form_data.get("status")
            status_code, result = update_exception_status(connection, idn, status)
        elif "create" in event["path"].split("/"):
            idn = event["pathParameters"].get("id")
            form_data = json.loads(event["body"])
            form_data["msg_code"] = "add_new"
            status_code, result = process_exceptions(connection, form_data, org_id, idn)
        elif "update" in event["path"].split("/"):
            idn = event["pathParameters"].get("id")
            form_data = json.loads(event["body"])
            form_data["msg_code"] = "update"
            status_code, result = process_exceptions(
                connection, form_data, org_id, idn, auth_user
            )
    return {
        "statusCode": status_code.value,
        "body": json.dumps(result, default=str),
        "headers": get_headers(),
    }
