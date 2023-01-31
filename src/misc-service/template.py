import os

import boto3
from custom_exception import GeneralException

s3_client = boto3.client("s3")

bucket_name = os.getenv("BUCKET_NAME")

"""
/api/carex/v1/disclaimer
/api/carex/v1/termsProviders
/api/carex/v1/eulaProviders
/api/carex/v1/privacy
"""

file_mapping = {
    "disclaimer": "disclaimer.html",
    "termsProviders": "termsProviders.html",
    "eulaProviders": "eulaProviders.html",
    "privacy": "privacy.html",
    "termsPatients": "termsPatients.html",
    "eulaPatients": "eulaPatients.html",
}


def lambda_handler(event, context):
    """
    Handler Function.
    """
    path = event["path"].split("/")
    print(path)
    file_name = ""
    if "disclaimer" in path:
        file_name = file_mapping["disclaimer"]
    elif "termsProviders" in path:
        file_name = file_mapping["termsProviders"]
    elif "eulaProviders" in path:
        file_name = file_mapping["eulaProviders"]
    elif "privacy" in path:
        file_name = file_mapping["privacy"]
    elif "termsPatients" in path:
        file_name = file_mapping["termsPatients"]
    elif "eulaPatients" in path:
        file_name = file_mapping["eulaPatients"]
    try:
        file_obj = s3_client.get_object(
            Bucket=bucket_name, Key="legal-docs/" + file_name
        )
        file_content = file_obj["Body"].read()
        status_code = 200
    except GeneralException as e:
        print(e)
        status_code = 400
        file_content = "Error"
    return {
        "statusCode": status_code,
        "body": file_content,
        "headers": {"Content-Type": "text/html"},
    }
