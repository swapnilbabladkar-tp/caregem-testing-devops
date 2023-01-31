import base64
import hashlib
import json
import logging
import os

import boto3
import unidecode
from botocore.exceptions import ClientError
from Crypto import Random
from Crypto.Cipher import AES
from custom_exception import GeneralException
from dotenv import load_dotenv
from shared import get_db_connect, read_as_dict

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s:%(message)s"
)
logger = logging.getLogger(__name__)

client = boto3.client("secretsmanager")

connection = get_db_connect()


def get_secret_manager(secret_id):
    """
    Get the details from Secrets Manager
    :param None
    :return: The key/value from Secret Manager
    """
    try:
        response = client.get_secret_value(SecretId=secret_id)
    except ClientError as e:
        if e.response["Error"]["Code"] == "DecryptionFailureException":
            logger.error(e)
        elif e.response["Error"]["Code"] == "InternalServiceErrorException":
            logger.error(e)
        elif e.response["Error"]["Code"] == "InvalidParameterException":
            logger.error(e)
        elif e.response["Error"]["Code"] == "InvalidRequestException":
            logger.error(e)
        elif e.response["Error"]["Code"] == "ResourceNotFoundException":
            logger.error(e)
    else:
        return json.loads(response["SecretString"])


encrypt_key = get_secret_manager(os.getenv("ENCRYPTION_KEY_SECRET_ID"))


def get_encryption_key():
    """
    This function:
    1. Gets Decryption key from AWS secret
    2. Encodes and converts the key to hash
    3. Returns the first 16 characters of the hash as the encryption key
    """
    if os.getenv("ENCRYPTION_KEY_SECRET_ID", None) is None:
        raise GeneralException("ENCRYPTION_KEY_SECRET_ID not set")
    else:
        if not encrypt_key:
            raise GeneralException("ENCRYPTION_KEY_SECRET_ID not set")
        key = hashlib.md5(
            encrypt_key["chat_encrypt_decrypt_key"].encode("utf-8")
        ).hexdigest()[:16]
    return key


def encrypt(plaintext):
    """
    This method is responsible to apply the AES encryption file and the Algorithm used is the AES
    """
    key = get_encryption_key()

    def pad(s):
        return s + (16 - len(s) % 16) * chr(16 - len(s) % 16)

    raw = pad(unidecode.unidecode(plaintext))
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(key.encode("utf8"), AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw.encode("utf-8"))).decode("utf-8")


def get_notification_details(cnx):
    """
    Returns list of notifications where  notification_details column value isnt NULL
    """
    query = """ SELECT id,notification_details FROM notifications  WHERE notification_details IS NOT null"""
    notifications = read_as_dict(cnx, query)
    if notifications:
        return notifications
    return None


def encrypt_notification_details(cnx):
    """To encrypt existing notification_details column in notifications table"""
    data = get_notification_details(connection)

    cursor = cnx.cursor()

    if data:
        for item in data:
            row = item["id"]
            val = encrypt(item["notification_details"])
            params = {"val": val, "row": row}
            sql = "UPDATE notifications SET notification_details = %(val)s WHERE id = %(row)s"
            cursor.execute(sql, params)

    cnx.commit()
    return data
