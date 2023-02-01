import json
import logging
from http import HTTPStatus

import pymysql
from custom_exception import GeneralException
from shared import get_db_connect, get_headers, read_as_dict, strip_dashes
from sqls.organization import GET_ORG, GET_ORG_LISTING, INSERT_ORG, UPDATE_ORG

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_org_listing(cnx):
    """
    Get the list of organizations
    """
    return HTTPStatus.OK, read_as_dict(cnx, GET_ORG_LISTING)


def get_org(cnx, org_id):
    """Get Organization by org_id"""
    organization = read_as_dict(cnx, GET_ORG, {"id": org_id}, fetchone=True)
    if organization and isinstance(organization, dict):
        organization.update(
            {
                "phone_1": strip_dashes(organization["phone_1"]),
                "phone_2": strip_dashes(organization.get("phone_2", "")),
            }
        )
        return HTTPStatus.OK, organization
    return HTTPStatus.NOT_FOUND, {}


def create_new_org(cnx, org_data):
    """
    Create new organization
    """
    try:
        params = {
            "name": org_data["name"],
            "email": org_data["email"],
            "phone_1": strip_dashes(org_data["phone_1"]),
            "phone_2": strip_dashes(org_data.get("phone_2", "")),
            "address": org_data["address"],
            "city": org_data["city"],
            "state": org_data["state"],
            "zipcode": org_data["zipcode"],
            "phone_1_country_code": org_data.get("phone_1_country_code", "+1"),
            "phone_2_country_code": org_data.get("phone_2_country_code", "+1"),
        }
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_ORG, params)
            org_id = cursor.lastrowid
            cnx.commit()
        return HTTPStatus.OK, read_as_dict(cnx, GET_ORG, {"id": org_id}, fetchone=True)
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err
    except GeneralException as exp:
        logger.exception(exp)
        return HTTPStatus.INTERNAL_SERVER_ERROR, exp


def update_org_data(cnx, org_data, org_id):
    """
    Update organization data
    """
    try:
        params = {
            "name": org_data["name"],
            "email": org_data["email"],
            "phone_1": org_data["phone_1"],
            "phone_2": org_data["phone_2"],
            "address": org_data["address"],
            "city": org_data["city"],
            "state": org_data["state"],
            "zipcode": org_data["zipcode"],
            "id": org_id,
            "phone_1_country_code": org_data.get("phone_1_country_code", "+1"),
            "phone_2_country_code": org_data.get("phone_2_country_code", "+1"),
        }
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_ORG, params)
            cnx.commit()
        return HTTPStatus.OK, read_as_dict(cnx, GET_ORG, {"id": org_id}, fetchone=True)
    except pymysql.MySQLError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err
    except GeneralException as exp:
        logger.exception(exp)
        return HTTPStatus.INTERNAL_SERVER_ERROR, exp


def lambda_handler(event, context):
    """
    The api will handle get org list and post,put org data
    """
    auth_user = event["requestContext"].get("authorizer")
    status_code = HTTPStatus.NOT_FOUND
    result = {}
    if auth_user["userRole"] == "super_admin":
        if event["httpMethod"] == "GET":
            if "orgs" in event["path"].split("/"):
                status_code, result = get_org_listing(connection)
            else:
                org_id = event["pathParameters"].get("org_id")
                status_code, result = get_org(connection, org_id)
        elif event["httpMethod"] == "POST":
            org_data = json.loads(event["body"])
            status_code, result = create_new_org(connection, org_data)
        elif event["httpMethod"] == "PUT":
            org_id = event["pathParameters"].get("org_id")
            org_data = json.loads(event["body"])
            status_code, result = update_org_data(connection, org_data, org_id)
    else:
        status_code = HTTPStatus.BAD_REQUEST
        result = "The user is not a Super Admin"
    return {
        "statusCode": status_code.value,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
