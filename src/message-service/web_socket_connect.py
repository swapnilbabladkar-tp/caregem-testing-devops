import json
import logging
from http import HTTPStatus

import boto3

dynamo_db = boto3.resource("dynamodb", region_name="us-east-1")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Lambda handler to connect websocket connection
    """
    logger.info(json.dumps(event))
    connection_id = event["requestContext"]["connectionId"]
    route_key = event["queryStringParameters"].get("routeKey")
    logger.info("Creating connection %s:: for route_key::%s", connection_id, route_key)
    user_conn = dynamo_db.Table("user_connections")
    payload = {"token": connection_id, "route_key": route_key}
    user_conn.put_item(Item=payload)
    logger.info(
        "Updated connection %s:: for route_key:: %s in dynamo db",
        connection_id,
        route_key,
    )
    return {"statusCode": HTTPStatus.OK, "body": json.dumps("Connected to Web Socket")}
