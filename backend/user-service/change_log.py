import decimal
import json
import logging
from http import HTTPStatus

import boto3
from botocore.exceptions import ClientError
from custom_exception import GeneralException
from shared import find_user_by_external_id, get_db_connect, get_headers, read_as_dict
from sqls.user import GET_CHANGE_LOG, GET_CUSTOMER_ADMIN_DETAILS

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")

user_pii_hist = dynamodb.Table("user_pii_hist")

connection = get_db_connect()


class DecimalEncoder(json.JSONEncoder):
    """
    Convert the Decimal into Str in Json object
    """

    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return str(o)
        return super().default(o)


def get_item_from_user_hist(external_id, version):
    """
    Returns the specified version of user data for given external_id
    """
    try:
        response = user_pii_hist.get_item(
            Key={"external_id": external_id, "version": version}
        )
    except ClientError as err:
        logger.error(err.response["Error"]["Message"])
    else:
        return response["Item"]


def get_auth_name_and_org(cnx, auth_id):
    """
    Returns Customer admin name and Org id for given customer admin DB id
    """
    return read_as_dict(cnx, GET_CUSTOMER_ADMIN_DETAILS, {"id": auth_id}, fetchone=True)


def get_user_change_log(cnx, user_id, user_role):
    """
    Returns Change log for given user id and role
    """
    change_logs = read_as_dict(
        cnx, GET_CHANGE_LOG, {"target_id": user_id, "target_role": user_role}
    )
    results = []
    for log in change_logs:
        try:
            sort_key = "v" + str(log["version"])
            external_id = log["external_id"]
            auth_user = {
                "utc_timestamp": log["utc_timestamp"].strftime(
                    "%a %b %d %Y %H:%M:%S %Z%zGMT"
                ),
                "auth_id": log["auth_id"],
                "auth_ipv4": log["auth_ipv4"],
                "auth_platform": log["auth_platform"],
                "auth_role": log["auth_role"],
                "external_id": log["external_id"],
                "id": log["id"],
            }
            auth_details = get_auth_name_and_org(cnx, log["auth_id"])
            auth_user["auth_name"] = auth_details.get("name", "Unknown")
            auth_user["auth_org_name"] = auth_details.get("org_name", "Unknown")
            profile_logs = get_item_from_user_hist(external_id, sort_key)
            profile_logs.update(auth_user)
            results.append(profile_logs)
        except GeneralException as exp:
            logger.exception(exp)
    return HTTPStatus.OK, results


def lambda_handler(event, context):
    """
    The api will handle the user creation
    """
    auth_user = event["requestContext"].get("authorizer")
    user_id = event["pathParameters"].get("user_id")
    user_role = event["pathParameters"].get("user_role")
    auth_user.update(
        find_user_by_external_id(
            connection, auth_user["userSub"], auth_user["userRole"]
        )
    )
    print(auth_user)
    status_code, user_result = get_user_change_log(connection, user_id, user_role)
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result, cls=DecimalEncoder),
        "headers": get_headers(),
    }
