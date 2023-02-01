import json
import logging
import os
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from custom_exception import GeneralException
from email_template import NewAdminEmail, RemovedAdminEmail, send_mail_to_user
from exceptions import InvalidNewUserError, OrganizationLimitError
from shared import (
    get_db_connect,
    get_headers,
    get_phi_data,
    get_phi_data_list,
    read_as_dict,
    strip_dashes,
)
from sqls.admin import (
    DELETE_CUSTOMER_ADMIN,
    GET_CUSTOMER_ADMIN_BY_ID,
    GET_CUSTOMER_ADMINS,
    INSERT_CUSTOMER_ADMIN,
    UPDATE_CUSTOMER_ADMIN,
)
from user_utils import (
    create_update_user_profile,
    create_user_in_cognito,
    format_user_fields,
    get_next_sequence,
    get_org_name,
    remove_user,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()

destination_email_list = os.getenv("DESTINATION_EMAIL_LIST")


def get_customer_admin_users_email(cnx, org_id):
    """
    Returns emails for all customer admins in the org
    """
    customer_admins = get_org_customer_admins(cnx, org_id)[1]
    if customer_admins:
        external_id_list = [admin["external_id"] for admin in customer_admins]
        phi_data_list = get_phi_data_list(external_id_list, dynamodb)
        return [item["email"] for item in phi_data_list.values()]
    return []


def send_deleted_user_notification(cnx, customer_admin):
    """Send notification to other customer Admins"""
    email_to_list = destination_email_list.split(",") if destination_email_list else []
    email_to_list.extend(get_customer_admin_users_email(cnx, customer_admin["org_id"]))
    org_details = get_org_name(cnx, customer_admin["org_id"])
    remove_admin_email = RemovedAdminEmail(
        org_details["name"], customer_admin["username"], customer_admin["email"]
    )
    for email in email_to_list:
        if email != customer_admin["email"]:
            send_mail_to_user([email], remove_admin_email)


def send_new_user_notification(cnx, customer_admin):
    """Send notification to other customer Admins"""
    email_to_list = destination_email_list.split(",") if destination_email_list else []
    email_to_list.extend(get_customer_admin_users_email(cnx, customer_admin["org_id"]))
    org_details = get_org_name(cnx, customer_admin["org_id"])
    new_admin_email = NewAdminEmail(
        org_details["name"], customer_admin["username"], customer_admin["email"]
    )
    # email_to_list = ["raj.shekhar@techprescient.com"]
    for email in email_to_list:
        if email != customer_admin["email"]:
            send_mail_to_user([email], new_admin_email)


def get_org_customer_admins(cnx, org_id):
    """Get customer admins of organization"""
    return HTTPStatus.OK, read_as_dict(cnx, GET_CUSTOMER_ADMINS, {"org_id": org_id})


def get_customer_admin_by_id(cnx, customer_admin_id):
    """
    Returns data for customer based on inout DB id
    """
    return read_as_dict(
        cnx, GET_CUSTOMER_ADMIN_BY_ID, {"id": customer_admin_id}, fetchone=True
    )


def get_customer_admin(cnx, customer_admin_id):
    """Get the customer admin by id"""
    customer_admin = get_customer_admin_by_id(cnx, customer_admin_id)
    if customer_admin and isinstance(customer_admin, dict):
        phi_data = get_phi_data(customer_admin["external_id"], dynamodb)
        customer_admin.update(phi_data if phi_data else {})
        customer_admin.update(
            {
                "cell_country_code": customer_admin.get("cell_country_code", "+1"),
                "office_tel_country_code": customer_admin.get(
                    "office_tel_country_code", "+1"
                ),
                "cell": strip_dashes(str(phi_data.get("cell", ""))) if phi_data else "",
                "office_tel": strip_dashes(str(phi_data.get("office_tel", "")))
                if phi_data
                else "",
            }
        )
        return HTTPStatus.OK, customer_admin
    return HTTPStatus.NOT_FOUND, None


def update_customer_admin(cnx, data, customer_admin_id):
    """Update customer admin"""
    try:
        customer_admin = get_customer_admin_by_id(cnx, customer_admin_id)
        profile_data = format_user_fields(data, "customer_admin")
        if customer_admin and isinstance(customer_admin, dict):
            profile_data["external_id"] = customer_admin["external_id"]
        upd_phi = create_update_user_profile(profile_data)
        if upd_phi:
            params = {
                "is_read_only": data["is_read_only"],
                "name": f"{upd_phi['first_name']} {upd_phi['last_name']}",
                "update_date": datetime.utcnow(),
                "id": customer_admin_id,
            }
            with cnx.cursor() as cursor:
                cursor.execute(UPDATE_CUSTOMER_ADMIN, params)
                cnx.commit()
            if customer_admin and isinstance(customer_admin, dict):
                customer_admin.update(upd_phi if upd_phi else {})
                customer_admin.update(
                    {
                        "cell_country_code": customer_admin.get(
                            "cell_country_code", "+1"
                        ),
                        "office_tel_country_code": customer_admin.get(
                            "office_tel_country_code", "+1"
                        ),
                    }
                )
        return HTTPStatus.OK, customer_admin
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err
    except GeneralException as exp:
        logger.exception(exp)
        return HTTPStatus.INTERNAL_SERVER_ERROR, exp


def add_customer_admin(cnx, data):
    """Create customer Admin"""
    customer_admin_id = None
    cognito_user = None
    phi_data = None
    try:
        name = data["first_name"] + " " + data["last_name"]
        org_name = get_org_name(cnx, data["org_id"]).get("name", "")
        code, cognito_user = create_user_in_cognito(
            data["username"], data["email"], name, org_name, "Admin"
        )
        if code != 200:
            raise InvalidNewUserError(code, cognito_user)
        user_sub = cognito_user.get("sub")
        profile_info = format_user_fields(data, "customer_admin")
        profile_info["external_id"] = user_sub
        phi_data = create_update_user_profile(profile_info)
        if phi_data:
            params = {
                "external_id": phi_data["external_id"],
                "internal_id": get_next_sequence(cnx),
                "name": name,
                "first_name": data["first_name"],
                "last_name": data["last_name"],
                "org_id": data["org_id"],
                "is_read_only": data["is_read_only"],
                "create_date": datetime.utcnow(),
            }
            with cnx.cursor() as cursor:
                cursor.execute(INSERT_CUSTOMER_ADMIN, params)
                customer_admin_id = cursor.lastrowid
                cnx.commit()
        customer_admin = get_customer_admin_by_id(cnx, customer_admin_id)
        if customer_admin and isinstance(customer_admin, dict):
            customer_admin.update(phi_data if phi_data else {})
            customer_admin.update(
                {
                    "cell_country_code": customer_admin.get("cell_country_code", "+1"),
                    "office_tel_country_code": customer_admin.get(
                        "office_tel_country_code", "+1"
                    ),
                }
            )
        logger.info("Customer Admin Created Successfully with id %s", customer_admin_id)
        send_new_user_notification(cnx, customer_admin)
        return HTTPStatus.OK, customer_admin
    except InvalidNewUserError as err:
        return err.code, err.msg
    except GeneralException as err:
        logger.error(err)
    if cognito_user or phi_data:
        remove_user(cognito_user, phi_data)
        if customer_admin_id:
            with cnx.cursor() as cursor:
                cursor.execute(DELETE_CUSTOMER_ADMIN, {"id": customer_admin_id})
                cnx.commit()
    return HTTPStatus.INTERNAL_SERVER_ERROR, "Error"


def delete_customer_admin(cnx, customer_admin_id):
    """Delete the customer admin by id"""
    try:
        customer_admin = get_customer_admin_by_id(cnx, customer_admin_id)
        other_customer_admins = []
        if customer_admin and isinstance(customer_admin, dict):
            other_customer_admins = get_org_customer_admins(
                cnx, customer_admin["org_id"]
            )[1]
        if other_customer_admins and len(other_customer_admins) == 0:
            raise OrganizationLimitError(
                "Cannot delete the last customer admin for the organization", 400
            )
        if customer_admin and isinstance(customer_admin, dict):
            phi_data = get_phi_data(customer_admin["external_id"])
            customer_admin.update(phi_data if phi_data else {})
            with cnx.cursor() as cursor:
                cursor.execute(DELETE_CUSTOMER_ADMIN, {"id": customer_admin["id"]})
                cnx.commit()
            remove_user(
                {"username": customer_admin["username"]},
                {"external_id": customer_admin["external_id"]},
            )
        send_deleted_user_notification(cnx, customer_admin)
        return HTTPStatus.OK, f"Customer Admin {customer_admin_id} updated Successfully"
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def lambda_handler(event, context):
    """
    Org portal Patient Handler
    """
    status_code = HTTPStatus.NOT_FOUND
    result = "Not Found"
    auth_user = event["requestContext"].get("authorizer")
    if auth_user["userRole"] == "super_admin":
        if event["httpMethod"] == "GET":
            if "admins" in event["path"].split("/"):
                org_id = event["pathParameters"].get("org_id")
                status_code, result = get_org_customer_admins(connection, org_id)
            else:
                customer_admin_id = event["pathParameters"].get("customer_admin_id")
                status_code, result = get_customer_admin(connection, customer_admin_id)
        elif event["httpMethod"] == "DELETE":
            customer_admin_id = event["pathParameters"].get("customer_admin_id")
            status_code, result = delete_customer_admin(connection, customer_admin_id)
        elif event["httpMethod"] == "POST":
            form_data = json.loads(event["body"])
            status_code, result = add_customer_admin(connection, form_data)
        elif event["httpMethod"] == "PUT":
            customer_admin_id = event["pathParameters"].get("customer_admin_id")
            form_data = json.loads(event["body"])
            status_code, result = update_customer_admin(
                connection, form_data, customer_admin_id
            )
    else:
        status_code = HTTPStatus.BAD_REQUEST
        result = "The user is not a Super Admin"
    return {
        "statusCode": status_code.value,
        "body": json.dumps(result, default=str),
        "headers": get_headers(),
    }
