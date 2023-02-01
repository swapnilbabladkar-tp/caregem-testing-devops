import json
import logging
from http import HTTPStatus

from shared import get_db_connect, get_headers, read_as_dict
from sqls.device import GET_UNPAIRED_DEVICES

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_unpaired_devices(cnx, imei):
    """
    Get Unpaired Devices.
    """
    active_devices = read_as_dict(cnx, GET_UNPAIRED_DEVICES, {"imei": imei})
    return HTTPStatus.OK, active_devices


def lambda_handler(event, context):
    """
    The api will handle user update, delete, read operations.
    """
    imei_id = event["pathParameters"].get("imei_id")
    status_code, result = get_unpaired_devices(connection, imei_id)
    return {
        "statusCode": status_code.value,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
