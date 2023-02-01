import json
import logging
from http import HTTPStatus

from shared import get_db_connect, get_headers, read_as_dict
from sqls.user import GET_DIAGNOSIS

logger = logging.getLogger(__name__)

connection = get_db_connect()


def load_diagnosis(cnx):
    """
    Get the Diagnosis List
    """
    result = read_as_dict(cnx, GET_DIAGNOSIS)
    return HTTPStatus.OK, result


def lambda_handler(event, context):
    """
    Handler Function
    """
    status_code, result = load_diagnosis(connection)
    return {
        "statusCode": status_code.value,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
