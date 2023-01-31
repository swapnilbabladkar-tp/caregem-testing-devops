import json
import logging
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from custom_exception import GeneralException
from exceptions import DataValidation, InvalidNewUserError
from log_changes import get_provider_log_state, log_change
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
from sqls.provider import (
    ACTIVATE_DEACTIVATE_PROVIDER,
    DELETE_PROVIDER_NETWORK,
    DELETE_PROVIDER_ORG,
    INSERT_PROVIDER,
    INSERT_PROVIDER_ORG,
    PROVIDER_DETAILS,
    PROVIDER_LISTING_QUERY,
    PROVIDER_UPDATE_QUERY,
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


def get_all_providers(
    cnx,
    auth_user,
    role=None,
    specialty=None,
    name_filter=None,
    page="0",
    page_size="100",
) -> tuple:
    """
    Get all the Providers based on role Associated to this Organization
    :params org_id, role
    :Return list of all providers associated to an organizations.
    """
    org_id = auth_user["userOrg"]
    specialty = "%" + specialty + "%" if specialty else None
    provider_data = read_as_dict(
        cnx,
        PROVIDER_LISTING_QUERY,
        {"role": role, "org_id": tuple([org_id]), "specialty": specialty},
    )
    provider_external_ids = [provider["external_id"] for provider in provider_data]
    phi_data = get_phi_data_list(provider_external_ids, dynamodb)
    for provider in provider_data:
        try:
            provider_info = phi_data[provider["external_id"]]
            name = (
                provider_info.get("first_name") + " " + provider_info.get("last_name")
            )
            provider.update(
                {
                    "name": name,
                    "first_name": provider_info.get("first_name"),
                    "last_name": provider_info.get("last_name"),
                    "picture": "https://weavers.space/img/default_user.jpg",
                    "role": provider_info.get("role"),
                }
            )
        except GeneralException as err:
            logger.error(err)
            return HTTPStatus.INTERNAL_SERVER_ERROR, err
    if name_filter:
        provider_data = list(
            filter(
                lambda provider: (name_filter.upper() in provider["name"].upper()),
                provider_data,
            )
        )

    no_name_filter_and_digit_page = (
        not name_filter
        and page_size
        and page
        and page_size.isdigit()
        and page.isdigit()
        and int(page_size) > 0
        and int(page) >= 0
    )
    if no_name_filter_and_digit_page:
        page_size = int(page_size)
        page = int(page)
        start = page * page_size
        stop = start + page_size
        provider_data = provider_data[start:stop]
    return HTTPStatus.OK, provider_data


def get_provider(cnx, provider_id: int, auth_user: dict) -> tuple:
    """Get patient Details"""
    org_id = auth_user["userOrg"]
    providers_details = read_as_dict(
        cnx, PROVIDER_DETAILS, {"provider_id": provider_id}, True
    )
    if not providers_details:
        return HTTPStatus.NOT_FOUND, "Provider doesn't Exist"
    providers_details["org"] = org_id
    phi_data = get_phi_data(providers_details["external_id"], dynamodb)
    providers_details.update(phi_data)
    providers_details.update(
        {
            "cell_country_code": phi_data.get("cell_country_code", "+1")
            if phi_data
            else "+1",
            "office_tel_country_code": phi_data.get("office_tel_country_code", "+1")
            if phi_data
            else "+1",
            "cell": strip_dashes(str(phi_data.get("cell", ""))) if phi_data else "",
            "office_tel": strip_dashes(str(phi_data.get("office_tel", "")))
            if phi_data
            else "",
        }
    )
    return HTTPStatus.OK, providers_details


def update_provider(cnx, provider_id: int, form_data: dict, auth_user: dict) -> tuple:
    """Update the provider"""
    try:
        restricted_fields = ["username"]
        provider = read_as_dict(
            cnx, PROVIDER_DETAILS, {"provider_id": provider_id}, fetchone=True
        )
        old_state = get_provider_log_state(cnx, provider_id)
        if not provider:
            return HTTPStatus.NOT_FOUND, "Provider Doesn't exist"
        prev_phi = get_phi_data(provider["external_id"], dynamodb)
        form_data["external_id"] = provider["external_id"]
        phi_data = prev_phi.copy()
        if prev_phi["email"] != form_data["email"] and get_user_via_email(
            form_data["email"], form_data["role"]
        ):
            raise InvalidNewUserError(
                101, "User with this email Already exists on system"
            )
        profile_data = format_user_fields(form_data, "providers")
        for attr in restricted_fields:
            profile_data.pop(attr)
        for attr in profile_data:
            phi_data.update({attr: form_data.get(attr) or ""})
        upd_phi = create_update_user_profile(phi_data)
        if prev_phi["email"] != upd_phi["email"]:
            if update_email_in_cognito(
                prev_phi["username"], form_data["email"], "WebApp"
            ):
                logger.info("Email Successfully updated In cognito")
        try:
            params = {
                "name": upd_phi["first_name"] + " " + upd_phi["last_name"],
                "remote_monitoring": form_data["remote_monitoring"],
                "update_date": datetime.utcnow(),
                "group": form_data["group_name"],
                "degree": form_data["degree"],
                "specialty": form_data["specialty"],
                "id": provider["id"],
            }
            with cnx.cursor() as cursor:
                cursor.execute(PROVIDER_UPDATE_QUERY, params)
                cnx.commit()
        except pymysql.MySQLError as err:
            logger.error(err)
            return HTTPStatus.INTERNAL_SERVER_ERROR, "Error while updating provider"
        new_state = get_provider_log_state(cnx, provider_id)
        log_change(cnx, old_state, new_state, auth_user, provider)
        return HTTPStatus.OK, {
            "id": provider["id"],
            "username": upd_phi["username"],
            "name": upd_phi["first_name"] + " " + upd_phi["last_name"],
            "first_name": upd_phi["first_name"],
            "last_name": upd_phi["last_name"],
            "role": "provider",
            "internal_id": provider["internal_id"],
            "remote_monitoring": provider["remote_monitoring"],
        }
    except InvalidNewUserError as err:
        return err.code, err.msg
    except GeneralException as err:
        logger.exception(err)
        if create_update_user_profile(prev_phi):
            logger.info("Previous Info Restored")
        return HTTPStatus.INTERNAL_SERVER_ERROR, "Error while Updating patient"


def delete_provider(cnx, provider_id: int, auth_user: dict) -> tuple:
    """
    This function:
    1. Gets provider data
    2. Archives Selected User
    3. Removed provider from all orgs
    4. Deletes provider network
    """
    org_id = auth_user["userOrg"]
    provider = read_as_dict(
        cnx, PROVIDER_DETAILS, {"provider_id": provider_id}, fetchone=True
    )
    if not provider:
        return HTTPStatus.NOT_FOUND, "Provider Not Found"
    try:
        with cnx.cursor() as cursor:
            params = {
                "role": "patient",
                "org_id": org_id,
                "user_id": provider["internal_id"],
            }
            cursor.execute(INSERT_DELETED_USER, params)
            cursor.execute(
                DELETE_PROVIDER_ORG, {"id": provider["id"], "org_id": org_id}
            )
            cnx.commit()
        orgs = get_user_org_ids(cnx, "providers", user_id=provider["id"])
        if not bool(orgs):
            with cnx.cursor() as cursor:
                cursor.execute(
                    DELETE_PROVIDER_NETWORK,
                    {"user_internal_id": provider["internal_id"]},
                )
                cursor.execute(
                    ACTIVATE_DEACTIVATE_PROVIDER, {"value": 0, "id": provider["id"]}
                )
                cnx.commit()
        else:
            _execute_network_fixes(cnx, provider["internal_id"], None)
        return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        cnx.rollback()
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def create_provider(cnx, form_data, auth_user):
    """
    This function:
    1. Creates user in cognito
    2. Inserts user phi data in dynamodb
    3. Inserts user in SQL table
    """
    try:
        org_id = auth_user["userOrg"]
        cognito_user = {}
        phi_data = {}
        name = form_data["first_name"] + " " + form_data["last_name"]
        org_name = get_org_name(cnx, org_id).get("name", "")
        code, cognito_user = create_user_in_cognito(
            form_data["username"], form_data["email"], name, org_name
        )
        if code != 200:
            raise InvalidNewUserError(code, cognito_user)
        user_sub = cognito_user.get("sub")
        profile_info = format_user_fields(form_data, "providers")
        profile_info["external_id"] = user_sub
        phi_data = create_update_user_profile(profile_info)
        params = {
            "external_id": phi_data["external_id"],
            "name": name,
            "internal_id": get_next_sequence(cnx),
            "ref_uid": form_data.get("ref_uid", None),
            "role": form_data["role"],
            "specialty": form_data["specialty"],
            "group": form_data["group_name"],
            "degree": form_data["degree"],
            "remote_monitoring": "N",
            "activated": 1,
        }
        provider_id = ""
        try:
            with cnx.cursor() as cursor:
                cursor.execute(INSERT_PROVIDER, params)
                provider_id = cursor.lastrowid
                cursor.execute(
                    INSERT_PROVIDER_ORG, {"org_id": org_id, "id": provider_id}
                )
                cnx.commit()
            logger.info(f"User Created Successfully with id {provider_id}")
        except pymysql.MySQLError as err:
            logger.error(err)
            cnx.rollback()
        return HTTPStatus.OK, {
            "id": provider_id,
            "last_name": phi_data["last_name"],
            "first_name": phi_data["first_name"],
            "name": phi_data["first_name"] + " " + phi_data["last_name"],
            "role": phi_data["role"],
            "username": phi_data["username"],
        }
    except InvalidNewUserError as e:
        return e.code, e.msg
    except GeneralException as err:
        logger.error(err)
        if cognito_user or phi_data:
            remove_user(cognito_user, phi_data)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def lambda_handler(event, context):
    """
    Org portal Patient Handler
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
        if "physicians" in path:
            status_code, result = get_all_providers(connection, auth_user, "physician")
        elif "nurses" in path:
            status_code, result = get_all_providers(connection, auth_user, "nurse")
        elif "case_managers" in path:
            status_code, result = get_all_providers(
                connection, auth_user, "case_manager"
            )
        elif "providers" in path:
            if auth_user.get("userOrg"):
                status_code, result = get_all_providers(connection, auth_user)
            else:
                patient_id = event["queryStringParameters"].get("patient_id")
                name_filter = event["queryStringParameters"].get("name_filter", "")
                specialty = event["queryStringParameters"].get("specialty", None)
                page = event["queryStringParameters"].get("page", 0)
                page_size = event["queryStringParameters"].get("pageSize", 100)
                user = find_user_by_external_id(connection, auth_user["userSub"])
                org_ids = get_common_org_id(connection, patient_id, user["internal_id"])
                auth_user["userOrg"] = org_ids
                status_code, result = get_all_providers(
                    connection, auth_user, None, specialty, name_filter, page, page_size
                )
        elif "provider" in path:
            provider_id = event["pathParameters"].get("provider_id")
            status_code, result = get_provider(connection, provider_id, auth_user)
    elif event["httpMethod"] == "PUT":
        provider_id = event["pathParameters"].get("provider_id")
        form_data = json.loads(event["body"])
        status_code, result = update_provider(
            connection, provider_id, form_data, auth_user
        )
    elif event["httpMethod"] == "DELETE":
        provider_id = event["pathParameters"].get("provider_id")
        status_code, result = delete_provider(connection, provider_id, auth_user)
    elif event["httpMethod"] == "POST":
        form_data = json.loads(event["body"])
        auth_user["userOrg"] = int(auth_user["userOrg"])
        user_data = {
            "username": form_data.get("username"),
            "first_name": form_data.get("first_name"),
            "last_name": form_data.get("last_name"),
            "cell_country_code": form_data.get("cell_country_code", "+1"),
            "office_tel_country_code": form_data.get("office_tel_country_code", "+1"),
            "cell": form_data.get("cell"),
            "email": form_data.get("email"),
            "address_city": form_data.get("address_city"),
            "state": form_data.get("state"),
            "address_zip": form_data.get("address_zip"),
            "dob": form_data.get("dob"),
            "drive_license_number": form_data.get("drive_license_number"),
            "msg": form_data.get("msg_code"),
            "external_id": form_data.get("external_id"),
            "degree": form_data.get("degree"),
            "specialty": form_data.get("specialty"),
            "group_name": form_data.get("group_name"),
            "office_tel": form_data.get("office_tel"),
            "office_addr_1": form_data.get("office_addr_1"),
            "office_addr_2": form_data.get("office_addr_2"),
            "year_grad_med_school": form_data.get("year_grad_med_school"),
            "role": form_data.get("role"),
        }
        DataValidation(user_data).validate_required_field(
            [
                "first_name",
                "last_name",
                "degree",
                "group_name",
                "office_tel",
                "office_addr_1",
                "address_city",
                "state",
                "address_zip",
                "email",
                "cell",
                "username",
            ]
        )
        status_code, result = create_provider(connection, user_data, auth_user)
    if isinstance(status_code, HTTPStatus):
        status_code = status_code.value
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
