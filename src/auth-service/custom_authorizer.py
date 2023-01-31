import enum
import json
import os

import boto3
import cognitojwt
from boto3.dynamodb.conditions import Key
from custom_exception import GeneralException

user_pool_id = os.environ.get("USER_POOL_ID")
aws_region = os.environ.get("DYNAMODB_REGION")
dynamodb_table_name = os.environ.get("POLICY_TABLE_NAME")
profile_table_name = os.environ.get("USER_PROFILE_TABLE_NAME")


def lambda_handler(event, context):
    """
    This function:
    1. Decodes Auth Token sent in API header
    2. Gets userSub,username and userProfile from the extracted token
    3. Gets userData from Dynamodb using userSub as the key
    4. Builds policy string for API gateway
    5. Creates and sets context data for the user
    6. Returns auth_response to use in event data for API's
    """
    try:
        print("Method ARN:- " + event["methodArn"])

        jwt_token = event["authorizationToken"]
        verified_claims = cognitojwt.decode(jwt_token, aws_region, user_pool_id)

        print("claims data:-")
        print(verified_claims)

        user_sub = get_user_sub(verified_claims)
        user_name = get_username(verified_claims)
        user_profile_id = get_user_profile_id(verified_claims)

        # get profile info
        user_profile = get_user_profile(user_sub)

        # get user role
        user_role = get_user_role(user_profile)
        if user_role == "customer_admin":
            user_org = get_org_id(user_profile)
        else:
            user_org = ""

        principal_id = "cognito|" + user_name
        print("Principle Id: " + principal_id)

        print("User Role -" + user_role)

        # if user_role == UserRole.NO_ROLE:
        #     return get_deny_policy(principal_id)

        tmp = event["methodArn"].split(":")
        arn_tmp = tmp[5].split("/")
        account_id = tmp[4]
        api_id = arn_tmp[0]
        api_stage = arn_tmp[1]

        # Build the policy
        policy_string = get_policy_for_user_role(
            user_role, principal_id, account_id, api_id, api_stage
        )
        auth_response = json.loads(policy_string)

        # set context
        context = {
            "userSub": user_sub,  # $context.authorizer.key -> value
            "userName": user_name,
            "userRole": user_role,
            "userOrg": user_org,
            "userProfile": user_profile_id,
        }
        auth_response["context"] = context
        # return policy - > this will be used by the api-gateway to grant permission
        return auth_response

    except GeneralException as e:
        print(e)
        return get_deny_policy("deny_policy")


def get_user_sub(verified_claims):
    """
    Returns sub property value from decoded JWT token
    """
    return verified_claims.get("sub")


def get_user_profile_id(verified_claims):
    """
    Returns profile property value from decoded JWT token
    """
    return verified_claims.get("profile")


def get_username(verified_claims):
    """
    Returns username property value from decoded JWT token
    """
    return verified_claims.get("username")


def get_user_role(user_profile):
    """
    Returns role property value from dynamodb user data
    """
    return user_profile["role"]


def get_org_id(user_profile):
    """
    Returns org_id property value from dynamodb user data
    """
    return int(user_profile.get("org_id"))


def get_deny_policy(principal_id):
    """
    Returns static deny policy object for entered principal id
    """
    return {
        "principalId": principal_id,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Deny",
                    "Resource": "arn:aws:execute-api:*:*:*/ANY/*",
                }
            ],
        },
        "context": {},
        "usageIdentifierKey": "{api-key}",
    }


def get_user_profile(user_sub):
    """
    Gets User data form dynamodb using input user_sub as key
    """
    dynamodb = boto3.resource("dynamodb", region_name=aws_region)
    table = dynamodb.Table(profile_table_name)
    response = table.get_item(Key={"external_id": user_sub})
    return response["Item"]


def get_policy_for_user_role(user_role, principal_id, account_id, api_id, api_stage):
    """
    This function:
    1. Gets Policy object from dynamodb based on user role
    2. Replaces placeholder values for:
        a) Principal ID
        b) Account ID
        c) API ID
        d) API Stage
       with input values to the function
    """
    dynamodb = boto3.resource("dynamodb", region_name=aws_region)
    table = dynamodb.Table(dynamodb_table_name)
    response = table.query(KeyConditionExpression=Key("group").eq(user_role))
    policy = response["Items"][0]["policy"]
    # Replace place-holders from the policy statement, if any
    placeholders_to_replace = {
        PolicyPlaceHolder.PRINCIPAL_ID: principal_id,
        PolicyPlaceHolder.ACCOUNT_ID: account_id,
        PolicyPlaceHolder.API_ID: api_id,
        PolicyPlaceHolder.API_STAGE: api_stage,
    }
    for key, value in placeholders_to_replace.items():
        policy = policy.replace(key.value, value)
    return policy


class PolicyPlaceHolder(enum.Enum):
    PRINCIPAL_ID = "PRINCIPAL_ID"
    ACCOUNT_ID = "ACCOUNT_ID"
    API_ID = "API_ID"
    API_STAGE = "API_STAGE"
