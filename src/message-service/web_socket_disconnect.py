import json
import logging

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamo_db = boto3.resource("dynamodb", region_name="us-east-1")


def lambda_handler(event, context):
    """
    Lambda handler to disconnect websocket connection
    """
    connection_id = event["requestContext"]["connectionId"]
    user_conn = dynamo_db.Table("user_connections")
    user_conn.delete_item(Key={"token": connection_id})
    logger.info("Disconnected connection :: %s", connection_id)
    return {"statusCode": 200, "body": json.dumps("Disconnected from Web Socket")}
