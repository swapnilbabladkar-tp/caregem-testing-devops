import base64
import json
import logging
import os

import boto3
import pymysql
import requests
from custom_exception import GeneralException
from db_ops import get_db_connect
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)

load_dotenv()

_TRUEVAULT_URL = "https://api.truevault.com/v1"

api_key = os.getenv("TRUEVAULT_API_KEY")
tv_vault_key = os.getenv("TRUEVAULT_USERS_LOG_VAULT_ID")

_USERS_LOG_VAULT_URL = "%s/vaults/%s/documents" % (
    _TRUEVAULT_URL,
    tv_vault_key,
)

dynamo_db = boto3.resource("dynamodb", region_name="us-east-1")


class ServerError(GeneralException):
    """
    Custom class for Server Error handling
    """

    def __init__(self, message, code=400):
        self.message = message
        self.code = code


def _auth_headers(content_type=None):
    """
    Custom header for fetching change log from Truevault
    """
    # api_key = base64.b64encode("%s:" % (api_key))
    headers = {"Authorization": "Basic %s" % api_key}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _raises_request_error(function):
    """
    Custom decorator function to fetch change log from Truevault
    """

    def decorator(*args, **kwargs):
        try:
            response = function(*args, **kwargs)
            print(response)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as http_error:
            error_code = response.json().get("error", {}).get("code", "")
            error_message = response.json().get("error", {}).get("message", "")
            raise ServerError(
                "%s:%s" % (error_code, error_message),
                code=http_error.response.status_code,
            )
        except GeneralException as e:
            raise ServerError(e.message)

    return decorator


@_raises_request_error
def _get(url):
    """
    Get Function Component for fetching change log from Truevault
    """
    return requests.get(url, headers=_auth_headers(), timeout=15)


def get_log_changes(doc_id):
    """
    Function to fetch Chnage log from truevault
    """
    url = "{}/{}".format(_USERS_LOG_VAULT_URL, doc_id)
    response = _get(url)

    changes_log = None
    if response and response.status_code == 200:
        changes_log = json.loads(base64.b64decode(response.text))

    return changes_log


def insert_user_to_hist(user_data, dynamodb=None):
    """
    Add the User Changes to Histroy Table.
    """
    if not dynamodb:
        dynamodb = boto3.resource("dynamodb")
    try:
        table = dynamodb.Table("user_pii_hist")
        external_id = user_data.pop("external_id")
        update_expression = (
            "SET Latest = if_not_exists(Latest, :defaultval) + :incrval,"
        )
        update_expression = update_expression + ",".join(
            f"#{k}=:{k}" for k in user_data
        )
        expression_attribute_values = {":defaultval": 0, ":incrval": 1}
        expression_attribute_values.update({f":{k}": v for k, v in user_data.items()})
        expression_attribute_names = {f"#{k}": k for k in user_data}
        response = table.update_item(
            Key={"external_id": external_id, "version": "v0"},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ReturnValues="UPDATED_NEW",
        )
        latest_version = response["Attributes"]["Latest"]
        user_data.update(
            {"version": "v" + str(latest_version), "external_id": external_id}
        )
        table.put_item(Item=user_data)
        return latest_version
    except GeneralException as e:
        logger.error(e)


def read_as_dict(connection, query, params=None):
    """
    Execute a select query and return the outcome as a dict
    """
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            if params:
                cursor.execute(query, (params))
            else:
                cursor.execute(query)
            return cursor.fetchall()
    except pymysql.MySQLError as err:
        logger.error(err)


def get_user_by_id(cnx, user_id, role):
    """
    Get User data for patient, caregiver,provider, customer_admin
    based on DB id and role
    """
    if role == "patient":
        query = """ SELECT external_id FROM patients where id = %s"""
    elif role in ("physician", "case_manager", "nurse"):
        query = """ SELECT external_id FROM providers where id = %s"""
    elif role == "caregiver":
        query = """ SELECT external_id FROM caregivers where id = %s"""
    elif role == "customer_admin":
        query = """ SELECT external_id FROM customer_admins where id = %s"""

    result = read_as_dict(cnx, query, (user_id))
    return result[0]


def update_change_log(cnx, external_id, id, version):
    """
    Update change log data
    """
    with cnx.cursor() as cursor:
        cursor.execute(
            "update change_log set external_id = %s, version = %s where id = %s",
            (external_id, version, id),
        )
        cnx.commit()


def get_and_save_change_log():
    """
    Function to extract all Change log data and update
    the external_id for user
    """
    cnx = get_db_connect()
    query = """ SELECT * FROM change_log """
    results = read_as_dict(cnx, query)
    for item in results:
        try:
            old_external_id = item["external_id"]
            user = get_user_by_id(cnx, item["target_id"], item["target_role"])
            new_external_id = user["external_id"]
            user_data = get_log_changes(old_external_id)
            user_data["old_state"]["external_id"] = new_external_id
            user_data["new_state"]["external_id"] = new_external_id
            user_data["external_id"] = new_external_id
            version = int(insert_user_to_hist(user_data, dynamo_db))
            update_change_log(cnx, new_external_id, item["id"], version)
        except GeneralException as e:
            print(e)
            print(item["target_id"], item["target_role"], user["external_id"])
