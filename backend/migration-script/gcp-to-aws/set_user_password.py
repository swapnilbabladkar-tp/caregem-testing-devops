import logging

import boto3

logger = logging.getLogger(__name__)

dynamo_db = boto3.resource("dynamodb", region_name="us-east-2")
client = boto3.client("cognito-idp", region_name="us-east-2")

user_pool_id = "us-east-2_L6pu3hhyL"
aws_region = "us-east-2"


def set_user_password(username, password):
    """
    Sets input password as the password in cognito for the input username
    """
    response = client.admin_set_user_password(
        UserPoolId=user_pool_id, Username=username, Password=password, Permanent=True
    )
    print(response)
