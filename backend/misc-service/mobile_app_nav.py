import json

import boto3

s3 = boto3.resource("s3")


def lambda_handler(event, context):
    """
    Handler file for misc service
    """
    content_object = s3.Object("caregem-mobile-app", "mobile_nav.json")
    file_content = content_object.get()["Body"].read().decode("utf-8")
    json_content = json.loads(file_content)
    print(json_content)
    return {
        "statusCode": 200,
        "body": json.dumps(json_content),
        "headers": {"Content-Type": "application/json"},
    }
