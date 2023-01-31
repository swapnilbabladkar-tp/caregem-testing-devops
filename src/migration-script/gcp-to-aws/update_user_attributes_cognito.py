import logging

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

user_pool_id = "us-east-1_iIWmJ2W2A"
aws_region = "us-east-1"

client = boto3.client("cognito-idp", region_name="us-east-1")


def update_email_verified_in_cognito(uname):
    """
    Sets cognito email for user as verified
    """
    try:
        client.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=uname,
            UserAttributes=[{"Name": "email_verified", "Value": "true"}],
        )
    except ClientError as e:
        print(e)
        logger.error(e)


def get_all_users_and_update_attr():
    """
    This Function:
    1. Gets list of all users in cognito
    2. Sets email as verified for all users
    """
    users = []
    next_page = None
    kwargs = {"UserPoolId": user_pool_id}

    users_remain = True
    while users_remain:
        if next_page:
            kwargs["PaginationToken"] = next_page
        response = client.list_users(**kwargs)
        users.extend(response["Users"])
        next_page = response.get("PaginationToken", None)
        users_remain = next_page is not None

    import pdb

    pdb.set_trace()
    for user in users:
        update_email_verified_in_cognito(user["Username"])
    return users
