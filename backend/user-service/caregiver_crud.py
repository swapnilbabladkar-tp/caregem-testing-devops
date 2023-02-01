import json
import logging
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from custom_exception import GeneralException
from exceptions import DataValidation, InvalidNewUserError
from log_changes import get_caregiver_log_state, log_change
from shared import (
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data,
    get_phi_data_list,
    get_user_org_ids,
    read_as_dict,
    strip_dashes,
)
from sqls.caregiver import (
    ACTIVATE_DEACTIVATE_CAREGIVER,
    DELETE_CAREGIVER_NETWORK,
    DELETE_CAREGIVER_ORG,
    GET_CAREGIVER_DETAILS,
    GET_CAREGIVER_LISTING,
    INSERT_CAREGIVER,
    INSERT_CAREGIVER_ORG,
    UPDATE_CAREGIVER_QUERY,
)
from sqls.user import INSERT_DELETED_USER
from user_utils import (
    _execute_network_fixes,
    create_update_user_profile,
    create_user_in_cognito,
    format_user_fields,
    get_next_sequence,
    get_org_name,
    get_user_via_email,
    remove_user,
    update_email_in_cognito,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()


def get_all_caregivers(cnx, auth_user: dict) -> tuple:
    """
    Get all the Caregivers Associated to this Organization
    :params org_id
    :Return list of all caregivers
    """
    org_id = auth_user["userOrg"]
    caregiver_data = read_as_dict(cnx, GET_CAREGIVER_LISTING, {"org_id": org_id})
    caregiver_external_ids = [caregiver["external_id"] for caregiver in caregiver_data]
    phi_data = get_phi_data_list(caregiver_external_ids, dynamodb)
    for caregiver in caregiver_data:
        try:
            caregiver_info = phi_data[caregiver["external_id"]]
            name = (
                caregiver_info.get("first_name") + " " + caregiver_info.get("last_name")
            )
            caregiver.update(
                {
                    "name": name,
                    "first_name": caregiver_info.get("first_name"),
                    "last_name": caregiver_info.get("last_name"),
                    "role": caregiver_info.get("role"),
                }
            )
        except GeneralException as err:
            logger.error(err)
    logger.info("Successfully fetched caregiver details for org_id %s", org_id)
    return 200, caregiver_data


def get_caregiver(cnx, caregiver_id: int, auth_user: dict) -> tuple:
    """
    Get caregiver Details
    :params caregiver_id, auth_user
    """
    caregiver_details = read_as_dict(
        cnx, GET_CAREGIVER_DETAILS, {"caregiver_id": caregiver_id}, True
    )
    if caregiver_details:
        phi_data = get_phi_data(caregiver_details["external_id"], dynamodb)
        if phi_data:
            caregiver_details.update(phi_data)
        caregiver_details.update(
            {
                "name": f"{phi_data.get('first_name','') if phi_data else ''} {phi_data.get('last_name','') if phi_data else ''}".strip(),
                "first_name": phi_data.get("first_name", "") if phi_data else "",
                "last_name": phi_data.get("last_name", "") if phi_data else "",
                "cell_country_code": phi_data.get("cell_country_code", "+1")
                if phi_data
                else "+1",
                "home_tel_country_code": phi_data.get("home_tel_country_code", "+1")
                if phi_data
                else "+1",
                "cell": strip_dashes(str(phi_data.get("cell", ""))) if phi_data else "",
                "home_tel": strip_dashes(str(phi_data.get("home_tel", "")))
                if phi_data
                else "",
            }
        )
        return HTTPStatus.OK, caregiver_details
    return HTTPStatus.NOT_FOUND, "Caregiver Doesn't Exist"


def update_caregiver(cnx, caregiver_id: int, form_data: dict, auth_user: dict) -> tuple:
    """
    Update the caregiver buy caregiver_id
    :params caregiver_id, form_data
    """
    try:
        restricted_fields = ["username"]
        caregiver = read_as_dict(
            cnx, GET_CAREGIVER_DETAILS, {"caregiver_id": caregiver_id}, fetchone=True
        )
        if not caregiver:
            return HTTPStatus.NOT_FOUND, "Caregiver Doesn't exist"
        old_state = get_caregiver_log_state(cnx, caregiver_id)
        prev_phi = get_phi_data(caregiver["external_id"], dynamodb)
        form_data["external_id"] = caregiver["external_id"]
        phi_data = prev_phi.copy()
        if prev_phi["email"] != form_data["email"] and get_user_via_email(
            form_data["email"], "caregiver"
        ):
            raise InvalidNewUserError(
                101, "User with this email Already exists on system"
            )
        profile_data = format_user_fields(form_data, "caregivers")
        for attr in restricted_fields:
            if attr in profile_data:
                profile_data.pop(attr)
        for attr in profile_data:
            phi_data.update({attr: form_data.get(attr) or ""})
        upd_phi = create_update_user_profile(phi_data)
        if prev_phi["email"] != upd_phi["email"]:
            if update_email_in_cognito(
                prev_phi["username"], upd_phi["email"], "WebApp"
            ):
                logger.info("Email Successfully updated In cognito")
        try:
            params = {
                "name": upd_phi["first_name"] + " " + upd_phi["last_name"],
                "update_date": datetime.utcnow(),
                "caregiver_id": caregiver["id"],
            }
            with cnx.cursor() as cursor:
                cursor.execute(UPDATE_CAREGIVER_QUERY, params)
                cnx.commit()
        except pymysql.MySQLError as err:
            logger.error(err)
            return HTTPStatus.INTERNAL_SERVER_ERROR, "Error while updating caregiver"
        new_state = get_caregiver_log_state(cnx, caregiver_id)
        caregiver["role"] = "caregiver"
        log_change(cnx, old_state, new_state, auth_user, caregiver)
        return HTTPStatus.OK, {
            "id": caregiver["id"],
            "username": upd_phi["username"],
            "name": upd_phi["first_name"] + " " + upd_phi["last_name"],
            "first_name": upd_phi["first_name"],
            "last_name": upd_phi["last_name"],
            "role": "caregiver",
            "internal_id": caregiver["internal_id"],
        }
    except InvalidNewUserError as err:
        return err.code, err.msg
    except GeneralException as err:
        logger.exception(err)
        if create_update_user_profile(prev_phi):
            logger.info("Previous Info Restored")
        return HTTPStatus.INTERNAL_SERVER_ERROR, "Error while Updating caregiver"


def delete_caregiver(cnx, caregiver_id: int, auth_user: dict) -> tuple:
    """Delete a caregiver"""
    org_id = auth_user["userOrg"]
    caregiver = read_as_dict(
        cnx, GET_CAREGIVER_DETAILS, {"caregiver_id": caregiver_id}, fetchone=True
    )
    if not caregiver:
        return HTTPStatus.NOT_FOUND, "Caregiver Not Found"
    try:
        with cnx.cursor() as cursor:
            params = {
                "role": "caregiver",
                "org_id": org_id,
                "user_id": caregiver["internal_id"],
            }
            cursor.execute(INSERT_DELETED_USER, params)
            cursor.execute(
                DELETE_CAREGIVER_ORG, {"id": caregiver["id"], "org_id": org_id}
            )
            cnx.commit()
        orgs = get_user_org_ids(cnx, "caregiver", user_id=caregiver["id"])
        if not bool(orgs):
            with cnx.cursor() as cursor:
                cursor.execute(
                    DELETE_CAREGIVER_NETWORK,
                    {"user_internal_id": caregiver["internal_id"]},
                )
                cursor.execute(
                    ACTIVATE_DEACTIVATE_CAREGIVER, {"value": 0, "id": caregiver["id"]}
                )
                cnx.commit()
        else:
            _execute_network_fixes(cnx, caregiver["internal_id"], None)
        return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        cnx.rollback()
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def create_caregiver(cnx, form_data: dict, auth_user: dict) -> tuple:
    """Create New caregiver"""
    try:
        cognito_user = {}
        phi_data = {}
        org_id = auth_user["userOrg"]
        name = form_data["first_name"] + " " + form_data["last_name"]
        org_name = get_org_name(cnx, org_id).get("name", "")
        code, cognito_user = create_user_in_cognito(
            form_data["username"], form_data["email"], name, org_name
        )
        if code != 200:
            raise InvalidNewUserError(code, cognito_user)
        user_sub = cognito_user.get("sub")
        profile_info = format_user_fields(form_data, "caregivers")
        profile_info["external_id"] = user_sub
        phi_data = create_update_user_profile(profile_info)
        params = {
            "external_id": phi_data["external_id"],
            "internal_id": get_next_sequence(cnx),
            "name": form_data["first_name"] + " " + form_data["last_name"],
            "create_date": datetime.utcnow(),
            "activated": 1,
        }
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_CAREGIVER, params)
            caregiver_id = cursor.lastrowid
            cursor.execute(INSERT_CAREGIVER_ORG, {"org_id": org_id, "id": caregiver_id})
            cnx.commit()
        response = {
            "id": caregiver_id,
            "last_name": phi_data["last_name"],
            "first_name": phi_data["first_name"],
            "name": phi_data["first_name"] + " " + phi_data["last_name"],
            "role": "caregiver",
            "username": phi_data["username"],
        }
        logger.info("Caregiver Created Successfully with id %s", caregiver_id)
        return HTTPStatus.OK, response
    except InvalidNewUserError as err:
        return err.code, err.msg
    except GeneralException as err:
        logger.error(err)
        if cognito_user or phi_data:
            remove_user(cognito_user, phi_data)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def lambda_handler(event, context):
    """
    Org portal Caregiver Handler
    """
    auth_user = event["requestContext"].get("authorizer")
    identity = event["requestContext"].get("identity")
    auth_user["ipv4"] = identity.get("sourceIp", None)
    path = event["path"].split("/")
    customer_admin = find_user_by_external_id(
        connection, auth_user["userSub"], auth_user["userRole"]
    )
    auth_user.update(customer_admin)
    if event["httpMethod"] == "GET":
        if "caregivers" in path:
            status_code, result = get_all_caregivers(connection, auth_user)
        elif "caregiver" in path:
            caregiver_id = event["pathParameters"].get("caregiver_id")
            status_code, result = get_caregiver(connection, caregiver_id, auth_user)
    elif event["httpMethod"] == "PUT":
        caregiver_id = event["pathParameters"].get("caregiver_id")
        form_data = json.loads(event["body"])
        status_code, result = update_caregiver(
            connection, caregiver_id, form_data, auth_user
        )
    elif event["httpMethod"] == "DELETE":
        caregiver_id = event["pathParameters"].get("caregiver_id")
        status_code, result = delete_caregiver(connection, caregiver_id, auth_user)
    elif event["httpMethod"] == "POST":
        form_data = json.loads(event["body"])
        auth_user["userOrg"] = int(auth_user["userOrg"])
        user_data = {
            "username": form_data.get("username"),
            "first_name": form_data.get("first_name"),
            "last_name": form_data.get("last_name"),
            "cell_country_code": form_data.get("cell_country_code", "+1"),
            "home_tel_country_code": form_data.get("home_tel_country_code", "+1"),
            "cell": form_data.get("cell"),
            "email": form_data.get("email"),
            "address_city": form_data.get("address_city"),
            "state": form_data.get("state"),
            "address_zip": form_data.get("address_zip"),
            "dob": form_data.get("dob"),
            "drive_license_number": form_data.get("drive_license_number"),
            "msg": form_data.get("msg_code"),
            "gender": form_data.get("gender"),
            "home_tel": form_data.get("home_tel"),
            "home_addr_1": form_data.get("home_addr_1"),
            "home_addr_2": form_data.get("home_addr_2"),
            "role": "caregiver",
        }
        DataValidation(user_data).validate_required_field(
            [
                "first_name",
                "last_name",
                "gender",
                "dob",
                "home_tel",
                "cell",
                "email",
                "home_addr_1",
                "address_city",
                "address_zip",
                "role",
            ]
        )
        status_code, result = create_caregiver(connection, user_data, auth_user)
        if isinstance(status_code, HTTPStatus):
            status_code = status_code.value
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
