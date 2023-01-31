import json
import logging
import re
from http import HTTPStatus

import boto3
from custom_exception import GeneralException
from shared import (
    User,
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data,
    get_phi_data_list,
    get_user_by_id,
    get_user_org_ids,
    read_as_dict,
)
from sqls.archived import (
    DELETE_USER_FROM_ARCHIVED,
    GET_ARCHIVED_USERS,
    GET_DELETED_USER,
    GET_DELETED_USER_BY_ORG_ID,
    GET_USER_BY_INTERNAL_ID,
    INSERT_USER_ORG,
)
from sqls.caregiver import ACTIVATE_DEACTIVATE_CAREGIVER
from sqls.patient import ACTIVATE_DEACTIVATE_PATIENT
from sqls.provider import ACTIVATE_DEACTIVATE_PROVIDER

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()


def get_deleted_user_details(cnx, user, internal_id):
    """
    Returns the User Details for a specific type User
    """
    query = GET_USER_BY_INTERNAL_ID.format(user=user)
    query = re.sub(r"\s+", " ", query)
    result = read_as_dict(cnx, query, {"internal_id": internal_id})
    return result


def get_all_the_deleted_user(cnx, org_id, internal_ids):
    """
    Returns all the deleted users
    """
    deleted_users = read_as_dict(cnx, GET_DELETED_USER_BY_ORG_ID, {"org_id": org_id})
    deleted_users_details = []
    for user in deleted_users:
        if user["user_internal_id"] in internal_ids:
            continue
        if user["role"] in ("physician", "case_manager", "nurse"):
            deleted_users_details.extend(
                get_deleted_user_details(cnx, "providers", user["user_internal_id"])
            )
        elif user["role"] == "patient":
            deleted_users_details.extend(
                get_deleted_user_details(cnx, "patients", user["user_internal_id"])
            )
        elif user["role"] == "caregiver" and user["user_internal_id"]:
            deleted_users_details.extend(
                get_deleted_user_details(cnx, "caregivers", user["user_internal_id"])
            )
    return deleted_users_details


def get_all_archived_users(cnx, org_id):
    """
    Get all the Archived User from the Organization
    :params cnx, org_id
    :Return list of all archived users
    """
    patient_query = GET_ARCHIVED_USERS.format(user="patients", user_org="patient_org")
    provider_query = GET_ARCHIVED_USERS.format(
        user="providers", user_org="provider_org"
    )
    caregiver_query = GET_ARCHIVED_USERS.format(
        user="caregivers", user_org="caregiver_org"
    )
    patients = read_as_dict(cnx, patient_query, {"org_id": org_id})
    providers = read_as_dict(cnx, provider_query, {"org_id": org_id})
    caregivers = read_as_dict(cnx, caregiver_query, {"org_id": org_id})
    archived_users = list(patients) + list(caregivers) + list(providers)
    internal_ids = [user["internal_id"] for user in archived_users]
    archived_users.extend(get_all_the_deleted_user(cnx, org_id, internal_ids))
    user_external_ids = [user["external_id"] for user in archived_users]
    user_external_ids = list(set(user_external_ids))
    phi_data = get_phi_data_list(user_external_ids, dynamodb)
    final_list = []
    for user in archived_users:
        try:
            user_info = phi_data.get(user["external_id"], {})
            archived_user = {
                "activated": user["activated"],
                "external_id": user["external_id"],
                "id": user["id"],
                "internal_id": user["internal_id"],
                "remote_monitoring": user.get("remote_monitoring", None),
                "role": user_info.get("role", ""),
                "specialty": user.get("specialty", ""),
                "degree": user.get("degree", ""),
                "username": user_info.get("username", ""),
                "name": user_info.get("first_name", "")
                + " "
                + user_info.get("last_name", ""),
                "first_name": user_info.get("first_name"),
                "last_name": user_info.get("last_name", ""),
                "alert_receiver": user.get("alert_receiver", None),
            }
            final_list.append(archived_user)
        except GeneralException as err:
            logger.error(err)
    return HTTPStatus.OK, final_list


def get_add_user_to_org_query(role):
    """
    Attach the users to their orgs
    :param role
    """
    if role in ("physician", "nurse", "case_manager"):
        org_table = "provider_org"
        org_column_name = "providers_id"
    elif role in "patient":
        org_table = "patient_org"
        org_column_name = "patients_id"
    elif role in "caregiver":
        org_table = "caregiver_org"
        org_column_name = "caregivers_id"
    return INSERT_USER_ORG.format(org_table=org_table, org_column_name=org_column_name)


def undelete_user(cnx, user_id, role, auth_user):
    """
    This Function:
    1. Gets User data
    2. Checks for orgs the user was a part of
    3. Removes user from deleted_users table
    4. Adds user to logged in user's org based on role if not already in one
    5. Returns user data
    """
    org_id = auth_user["userOrg"]
    user = get_user_by_id(cnx, user_id, role)
    if not user:
        logger.error("User with Given ID doesn't Exist")
        return HTTPStatus.NOT_FOUND, "User with given id does not exist"
    user = user[0]
    orgs = get_user_org_ids(cnx, role, user_id=user_id)
    already_in_org = None
    user_param = {"internal_id": user["internal_id"], "org_id": org_id}
    if user["activated"] and len(orgs) > 0:
        if org_id in orgs:
            del_user = read_as_dict(cnx, GET_DELETED_USER, user_param, fetchone=True)
            if del_user:
                with cnx.cursor() as cursor:
                    cursor.execute(DELETE_USER_FROM_ARCHIVED, {"id": del_user["id"]})
                cnx.commit()
            already_in_org = True
    if not already_in_org:
        del_user = read_as_dict(cnx, GET_DELETED_USER, user_param, fetchone=True)
        if del_user:
            add_user_to_org = get_add_user_to_org_query(role)
            with cnx.cursor() as cursor:
                cursor.execute(
                    add_user_to_org, {"org_id": org_id, "user_id": user["id"]}
                )
                params = {"value": 1, "id": user["id"]}
                if User.is_provider(role):
                    cursor.execute(ACTIVATE_DEACTIVATE_PROVIDER, params)
                elif role == "patient":
                    cursor.execute(ACTIVATE_DEACTIVATE_PATIENT, params)
                elif role == "caregiver":
                    cursor.execute(ACTIVATE_DEACTIVATE_CAREGIVER, params)
                cursor.execute(DELETE_USER_FROM_ARCHIVED, {"id": del_user["id"]})
            cnx.commit()
    undeleted_user = {
        "id": user["id"],
        "external_id": user["external_id"],
        "role": role,
    }
    if User.is_provider(role):
        undeleted_user["specialty"] = user["specialty"]
    phi_data = get_phi_data(user["external_id"], dynamodb)
    if phi_data:
        undeleted_user["name"] = phi_data["first_name"] + " " + phi_data["last_name"]
        undeleted_user["first_name"] = phi_data["first_name"]
        undeleted_user["last_name"] = phi_data["last_name"]
    return HTTPStatus.OK, undeleted_user


def lambda_handler(event, context):
    """
    Handler Function for archived
    """
    auth_user = event["requestContext"].get("authorizer")
    if event["httpMethod"] == "GET":
        status_code, user_result = get_all_archived_users(
            connection, auth_user["userOrg"]
        )
    elif event["httpMethod"] == "PUT":
        role = event["queryStringParameters"].get("type")
        user_id = event["pathParameters"].get("user_id")
        auth_user.update(
            find_user_by_external_id(
                connection, auth_user["userSub"], auth_user["userRole"]
            )
        )
        status_code, user_result = undelete_user(connection, user_id, role, auth_user)
    if isinstance(status_code, HTTPStatus):
        status_code = status_code.value
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
