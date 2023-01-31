import boto3

client = boto3.client("chime")


def create_app_instance(name):
    """
    Create a Chime App instance and return response object with the ARN
    """
    response = client.create_app_instance(
        Name=name, Metadata="string", ClientRequestToken="string"
    )
    return response


create_app_instance("caregem-chime-arn")
