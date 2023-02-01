import json
import logging

from shared import get_db_connect, get_headers, read_as_dict
from sqls.remote_monitoring import REMOTE_BILLING_PROVIDERS

connection = get_db_connect()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_rm_billing_providers(cnx, org_id):
    """RM billing Providers"""
    result = read_as_dict(cnx, REMOTE_BILLING_PROVIDERS, {"org_id": org_id})
    return result


def lambda_handler(event, context):
    """
    Handler function for remote billing providers
    """
    auth_user = event["requestContext"].get("authorizer")
    result = get_rm_billing_providers(connection, auth_user["userOrg"])
    return {"statusCode": 200, "body": json.dumps(result), "headers": get_headers()}
