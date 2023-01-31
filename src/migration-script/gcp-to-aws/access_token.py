import os

import boto3
from dotenv import load_dotenv

load_dotenv()
client = boto3.client("cognito-idp", region_name="us-east-1")

CLIENT_ID = os.getenv("CLIENT_ID")


def initiate_auth(username, password):
    """
    Returns access token from cognito when passed username and password as input
    """
    response = client.initiate_auth(
        ClientId="7519k85s7id8n5cqh68f595vgp",
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": username, "PASSWORD": password},
    )
    return response["AuthenticationResult"]["AccessToken"]
