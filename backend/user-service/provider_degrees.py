import json
import logging
from http import HTTPStatus

from custom_exception import GeneralException
from shared import get_db_connect, get_headers, read_as_dict
from sqls.provider import GET_PROVIDER_DEGREES

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
connection = get_db_connect()


def get_provider_degrees():
    """
    Returns list of degrees for provider
    """
    try:
        provider_degrees = read_as_dict(connection, GET_PROVIDER_DEGREES)
    except GeneralException as e:
        logging.exception(e)

    provider_degrees_list = []
    try:
        provider_degrees_list = [
            item.get("provider_degree") for item in provider_degrees if item
        ]
        if provider_degrees_list:
            return HTTPStatus.OK, provider_degrees_list
    except KeyError as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err
    except GeneralException as err:
        logger.error(err)
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def lambda_handler(event, context):
    """
    The api will return a list of provider degrees
    """
    status_code, provider_degrees = get_provider_degrees()
    return {
        "statusCode": status_code,
        "body": json.dumps(provider_degrees),
        "headers": get_headers(),
    }
