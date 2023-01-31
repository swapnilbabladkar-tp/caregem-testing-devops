import json
import logging
from http import HTTPStatus

import pymysql
from custom_exception import GeneralException
from shared import get_db_connect, get_headers, read_as_dict
from sqls.provider import PROVIDER_DETAILS
from sqls.user import (
    NETWORK_USER_BY_USER_ID,
    UPDATE_NETWORK_ALERT_STATUS,
    UPDATE_PROVIDER_ALERT_STATUS,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def update_alert_receiver_flag(cnx, provider_id, alert_status):
    """
    Update the Alert for a provider
    :params provider_id, alert_status 0,1
    :Return Msg String for update
    """
    provider = read_as_dict(
        cnx, PROVIDER_DETAILS, {"provider_id": provider_id}, fetchone=True
    )
    prv_network = read_as_dict(
        cnx, NETWORK_USER_BY_USER_ID, {"user_id": provider["internal_id"]}
    )
    network_ids = [network["id"] for network in prv_network]
    try:
        with cnx.cursor() as cursor:
            cursor.execute(
                UPDATE_PROVIDER_ALERT_STATUS,
                {"alert_status": alert_status, "provider_id": provider_id},
            )
            if network_ids:
                cursor.execute(
                    UPDATE_NETWORK_ALERT_STATUS,
                    {"alert_status": alert_status, "network_ids": tuple(network_ids)},
                )
            cnx.commit()
        return HTTPStatus.OK, f"Status changed successfully for provider {provider_id}"
    except pymysql.MySQLError as err:
        logger.error(err)
    except GeneralException as exp:
        logger.exception(exp)
    return HTTPStatus.INTERNAL_SERVER_ERROR, "Error"


def lambda_handler(event, context):
    """
    The api will handle user update, delete, read operations.
    """
    provider_id = event["pathParameters"].get("prv_id")
    form_data = json.loads(event["body"])
    alert_receiver_status = 1 if int(form_data["alert_receiver_status"]) else 0
    status_code, user_result = update_alert_receiver_flag(
        connection, provider_id, alert_receiver_status
    )
    return {
        "statusCode": status_code.value,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
