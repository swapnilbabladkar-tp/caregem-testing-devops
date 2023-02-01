import json
import logging

import boto3
from custom_exception import GeneralException
from shared import (
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data_list,
    get_user_org_ids,
    read_as_dict,
)
from sqls.provider_data import ALL_NETWORK_SAME_PATIENT, LIST_PROVIDERS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()


def get_provider_same_org_network(cnx, internal_id, role, specialty=None):
    """
    This Function:
    1. Gets list of all users in the network of the input user's patients
    2. Gets Org Ids of the network users
    3. Returns data for all network users as list
    """
    connected_user = read_as_dict(
        cnx, ALL_NETWORK_SAME_PATIENT, {"user_id": internal_id}
    )
    connected_user_internal_ids = [row["internal_id"] for row in connected_user]
    org_ids = get_user_org_ids(cnx, role, internal_id=internal_id)
    params = {
        "org_ids": tuple(org_ids),
        "connected_user_internal_ids": tuple(connected_user_internal_ids)
        if (len(connected_user_internal_ids) > 0)
        else tuple([-1]),
        "internal_id": internal_id,
        "role": role,
        "specialty": "%" + specialty + "%" if specialty else None,
    }
    result = read_as_dict(cnx, LIST_PROVIDERS, params)
    return result


def get_provider_list(
    cnx, user, role, page=None, page_size=None, name_filter=None, specialty=None
):
    """
    Get the providers based on role.
    """
    providers = get_provider_same_org_network(cnx, user["internal_id"], role, specialty)
    unique_providers = list(
        {provider["id"]: provider for provider in providers}.values()
    )
    provider_external_ids = list(set([prv["external_id"] for prv in providers]))
    phi_data = get_phi_data_list(provider_external_ids, dynamodb)
    results = []
    try:
        for prv in unique_providers:
            profile_data = phi_data[prv["external_id"]]
            prv_obj = {
                "id": str(prv["internal_id"]),
                "name": (profile_data["first_name"] + " " + profile_data["last_name"]),
                "group": prv["grp"],
                "role": prv["role"],
                "specialty": prv["specialty"],
                "last_name": profile_data["last_name"],
                "first_name": profile_data["first_name"],
                "degree": prv["degree"],
                "picture": "https://weavers.space/img/default_user.jpg",
            }
            if prv["degree"]:
                prv_obj["name"] = prv_obj["name"] + ", " + prv["degree"]
            results.append(prv_obj)
    except GeneralException as err:
        logger.error(err)
    # sort items by previously added last_name
    results = sorted(results, key=lambda p: p.get("last_name"))
    if name_filter:
        results = list(
            filter(
                lambda provider: (name_filter.upper() in provider["name"].upper()),
                results,
            )
        )
    if (
        not name_filter
        and str(page).isdigit()
        and str(page_size).isdigit()
        and int(page_size) > 0
        and int(page) >= 0
    ):
        start = page * page_size
        stop = start + page_size
        results = results[start:stop]
    return results


def lambda_handler(event, context):
    """
    The api will handle Get Network for providers and caregivers.
    """
    # auth_user = get_logged_in_user(cognito_user["sub"], None)
    auth_user = event["requestContext"].get("authorizer")
    query_params = (
        event["queryStringParameters"] if event["queryStringParameters"] else {}
    )
    page = query_params.get("page", 0)
    page_size = query_params.get("pageSize", 100)
    specialty = query_params.get("specialty", None)
    name_filter = query_params.get("name_filter", None)
    if "physicians" in event["path"].split("/"):
        role = "physician"
    elif "case_managers" in event["path"].split("/"):
        role = "case_manager"
    elif "nurses" in event["path"].split("/"):
        role = "nurse"
    else:
        role = "providers"
    user = find_user_by_external_id(connection, auth_user["userSub"], "providers")
    result = get_provider_list(
        connection, user, role, page, page_size, name_filter, specialty
    )
    return {
        "statusCode": 200,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
