import json
import logging

from shared import get_db_connect, get_headers, read_as_dict
from sqls.call import CALL_NOTES

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def get_call_notes(cnx):
    """Get the call log notes"""
    return read_as_dict(cnx, CALL_NOTES)


def lambda_handler(event, context):
    """
    Handler Function
    """
    return {
        "statusCode": 200,
        "body": json.dumps(get_call_notes(connection)),
        "headers": get_headers(),
    }
