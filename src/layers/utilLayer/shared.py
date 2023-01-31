import base64
import functools
import hashlib
import json
import logging
import os
import sys
import time
from datetime import date
from enum import Enum
from typing import Union

import boto3
import cognitojwt
import pymysql
import unidecode
from botocore.exceptions import ClientError
from cognitojwt.exceptions import CognitoJWTException
from Crypto import Random
from Crypto.Cipher import AES
from custom_exception import GeneralException
from dateutil import tz
from dotenv import load_dotenv
from utils_query import GET_LINKED_PATIENTS_OF_PROVIDER

load_dotenv()

mlprep_secret_name = os.getenv("MLPREP_SECRET_NAME")
db_secret_name = os.getenv("DB_SECRET_NAME")
dynamodb_region = os.getenv("DYNAMODB_REGION")
aws_region = os.getenv("AWSREGION")
profile_table = os.getenv("USER_PROFILE_TABLE_NAME")
user_pool_id = os.getenv("USER_POOL_ID")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s:%(message)s"
)
logger = logging.getLogger(__name__)

client = boto3.client("secretsmanager")


class User(Enum):
    """
    User Class
    """

    PHYSICIAN_USER = "physician"
    CASE_MANAGER_USER = "case_manager"
    NURSE_USER = "nurse"
    PATIENT_USER = "patient"
    CAREGIVER_USER = "caregiver"
    PROVIDER_ROLES = (PHYSICIAN_USER, NURSE_USER, CASE_MANAGER_USER)
    PATIENT_ROLES = (PATIENT_USER, CAREGIVER_USER)

    @staticmethod
    def is_provider(role):
        """
        Check if input role is present in the PROVIDER_ROLES list
        """
        return role in User.PROVIDER_ROLES.value

    @staticmethod
    def is_patient(role):
        """
        Check if input role is 'patient'
        """
        return role == User.PATIENT_USER.value

    @staticmethod
    def is_caregiver(role):
        """
        Check if input role is 'caregiver'
        """
        return role == User.CAREGIVER_USER.value


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


def get_headers():
    """
    Get the headers to add to response data
    """
    HEADERS = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
    }
    return HEADERS


def get_db_connect():
    """
    Returns PyMysql Connection object.
    :param None
    :return: db connection.
    """
    connection = None
    db_details = get_secret_manager(db_secret_name)
    # The following used as for local connection will be commented
    # db_details = {
    #     "host": "localhost",
    #     "username": "root",
    #     "password": "password",
    #     "dbname": "carex",
    # }
    try:
        if not connection:
            connection = pymysql.connect(
                host=db_details["host"],
                user=db_details["username"],
                passwd=db_details["password"],
                db=db_details["dbname"],
                connect_timeout=5,
            )
    except pymysql.MySQLError as err:
        logger.error(err)
        sys.exit()
    else:
        return connection


def get_analytics_connect():
    """
    Returns PyMysql Connection object.
    :param None
    :return: db connection.
    """
    connection = None
    db_details = get_secret_manager(mlprep_secret_name)
    # The following used as for local connection will be commented
    # db_details = {
    #     "host": "localhost",
    #     "username": "root",
    #     "password": "password",
    #     "dbname": "mlprep",
    # }
    try:
        if not connection:
            connection = pymysql.connect(
                host=db_details["host"],
                user=db_details["username"],
                passwd=db_details["password"],
                db=db_details["dbname"],
                connect_timeout=5,
            )
    except pymysql.MySQLError as err:
        logger.error(err)
        sys.exit()
    else:
        return connection


def read_query(connection, query, params=None):
    """
    Execute the Select Query and return the result
    """
    try:
        with connection.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            result = cursor.fetchall()
            connection.commit()
            return result
    except pymysql.MySQLError as err:
        logger.error(err)


def read_as_dict(connection, query, params=None, fetchone=None):
    """
    Execute a select query and return the outcome as a dict
    """
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query, params) if params else cursor.execute(query)
            result = cursor.fetchone() if fetchone else cursor.fetchall()
            connection.commit()
            if result:
                return result
            if fetchone:
                return {}
            return []
    except pymysql.MySQLError as err:
        logger.exception(err)


def json_response(data, response_code=200):
    """
    Lambda Response
    """
    return {
        "statusCode": response_code,
        "body": json.dumps(data),
        "headers": get_headers(),
    }


def get_next_sequence(connection):
    """
    Returns the next from id_sequence Table to be used as internal id.
    """
    query = """ INSERT INTO id_sequences (id) VALUES (0) """
    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            connection.commit()
        return cursor.lastrowid
    except pymysql.MySQLError as err:
        logger.error(err)


def get_internal_id(connection, table_name, id):
    """
    Returns the internal id
    """
    query = """ SELECT internal_id from {table_name} where id = %s
            """.format(
        table_name=table_name
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (id))
            return cursor.fetchone()[0]
    except pymysql.MySQLError as err:
        logger.error(err)


def get_db_id_from_internal_id(connection, table_name, id):
    """
    Returns the Auto generated db id from internal id
    """
    query = """ SELECT id from {table_name} where internal_id = %s
            """.format(
        table_name=table_name
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (id))
            return cursor.fetchone()[0]
    except pymysql.MySQLError as err:
        logger.error(err)


def get_db_id_from_external_id(connection, table_name, external_id):
    """
    Returns the Auto generated db id from internal id
    """
    query = """ SELECT id from {table_name} where external_id = %s
            """.format(
        table_name=table_name
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (external_id))
            return cursor.fetchone()[0]
    except pymysql.MySQLError as err:
        logger.error(err)


def timer(func):
    """
    Function creates a timer wrapper for the function passed as the input
    """

    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        tic = time.perf_counter()
        value = func(*args, **kwargs)
        toc = time.perf_counter()
        elapsed_time = toc - tic
        print(f"Elapsed time: {elapsed_time:0.4f} seconds")
        return value

    return wrapper_timer


def get_logged_in_user(access_token, dynamodb=None):
    """
    Get the Logged in User details
    :param access token key, dynamodb_instance
    :return: User Sepcific Details
    This is basically developed for local debugging,
    ideally the user details will be fetched from authorizer
    """
    try:
        cognito_user = cognitojwt.decode(access_token, aws_region, user_pool_id)
    except CognitoJWTException as e:
        raise e
    external_id = cognito_user["sub"]
    auth_user = {}
    if not dynamodb:
        dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(profile_table)
    try:
        response = table.get_item(Key={"external_id": external_id})
        if response.get("Item"):
            dynamo_user = response["Item"]
            if dynamo_user.get("org_id"):
                auth_user["userOrg"] = int(dynamo_user.get("org_id"))
            auth_user["name"] = (
                dynamo_user["first_name"] + " " + dynamo_user["last_name"]
            )
            auth_user["first_name"] = dynamo_user["first_name"]
            auth_user["last_name"] = dynamo_user["last_name"]
            auth_user["userRole"] = dynamo_user["role"]
            auth_user["userSub"] = external_id
        return auth_user
    except ClientError as e:
        logging.error(e.response["Error"]["Message"])


def get_phi_data(external_id, dynamodb=None):
    """
    Get the user PHI data based on external id/user sub
    :param partition key, dynamodb_instance
    :return: PHI data for User
    """
    if not dynamodb:
        dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(profile_table)
    try:
        response = table.get_item(Key={"external_id": external_id})
    except ClientError as e:
        logging.error(e.response["Error"]["Message"])
    else:
        if response.get("Item"):
            return response["Item"]
        return None


def chunks(lst, n):
    """
    Yield successive n-sized chunks from list.
    """
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def get_phi_data_list(external_ids, dynamodb=None):
    """
    Get the user PHI data based on external id/user sub
    :param partition key, dynamodb_instance
    :return: PHI data for User
    """
    external_id_in_chunks = chunks(external_ids, 50)
    phi_data = {}
    for external_ids in external_id_in_chunks:
        keys = [{"external_id": external_id} for external_id in external_ids]
        if not dynamodb:
            dynamodb = boto3.resource("dynamodb", dynamodb_region)
        try:
            response = dynamodb.batch_get_item(
                RequestItems={"user_pii": {"Keys": keys, "ConsistentRead": True}},
                ReturnConsumedCapacity="TOTAL",
            )
        except ClientError as e:
            logger.error(e.response["Error"]["Message"])
        else:
            items = response["Responses"]["user_pii"]
            for item in items:
                phi_data[item["external_id"]] = item
    return phi_data
    # print(json.dumps(item, indent=4, cls=DecimalEncoder))


def get_the_org_ids(connection, external_id, user_type):
    """
    Get the user Org Id based on external id/user sub
    :param: external_id
    :return:List of orgs user is associated with
    """
    if user_type in ("physician", "case_manager", "nurse"):
        table_name = "providers"
        org_table_name = "provider_org"
        org_column = "providers_id"
    elif user_type == "patient":
        table_name = "patients"
        org_table_name = "patient_org"
        org_column = "patients_id"
    elif user_type == "caregiver":
        table_name = "caregivers"
        org_table_name = "caregiver_org"
        org_column = "caregivers_id"

    query = """ SELECT organizations_id
            FROM   {table_name}
            JOIN   {org_table_name}
            ON     {table_name}.id = {org_table_name}.{org_column}
            WHERE  {table_name}.external_id = %s
        """.format(
        table_name=table_name, org_table_name=org_table_name, org_column=org_column
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, (external_id))
            result = [item[0] for item in cursor.fetchall()]
            return result
    except pymysql.MySQLError as err:
        logger.error(err)


def utc_to_cst(datetime):
    """
    Converts UTC datetime to CST
    """
    from_zone = tz.gettz("UTC")
    to_zone = tz.gettz("America/Chicago")
    datetime = datetime.replace(tzinfo=from_zone)
    return datetime.astimezone(to_zone)


def get_user_details_from_external_id(cnx, external_id):
    """
    Returns user data based on external_id
    in patients / providers / patients Tables
    Returns empty list if not found
    """
    query = """ SELECT * FROM providers WHERE external_id=%s """
    result = read_as_dict(cnx, query, (external_id))
    if result:
        return result[0]
    query = """ SELECT * FROM patients WHERE external_id=%s """
    result = read_as_dict(cnx, query, (external_id))
    if result:
        return result[0]
    query = """ SELECT * FROM caregivers WHERE external_id=%s """
    result = read_as_dict(cnx, query, (external_id))
    if result:
        return result[0]
    return []


def get_org_ids_from_ext_id(cnx, external_id, role):
    """
    Returns list of org ids for the user with the input external_id and role
    """
    if role == "patient":
        org_column = "patients_id"
        org_table = "patient_org"
        table = "patients"
    elif role in ("physician", "nurse", "case_manager"):
        org_column = "providers_id"
        org_table = "provider_org"
        table = "providers"
    elif role == "caregiver":
        org_table = "caregiver_org"
        org_column = "caregivers_id"
        table = "caregivers"
    query = """ SELECT GROUP_CONCAT({org_table}.organizations_id) as org_ids
                FROM {table}
                INNER JOIN {org_table}
                ON {table}.id = {org_table}.{org_column}
                WHERE {table}.external_id = %s
                GROUP BY {table}.id
                """.format(
        table=table, org_column=org_column, org_table=org_table
    )
    org_ids = read_query(cnx, query, (external_id))
    return [org[0] for org in org_ids]


def find_user_by_internal_id(cnx, internal_id, role=None):
    """
    Returns user data based on input internal_id and role(optional)
    If role isnt passed then the function will search for user
    internal_id in providers / caregivers / patients Tables
    """
    user_types = ["providers", "patients", "caregivers"]
    user_table = None
    if role:
        if role in User.PROVIDER_ROLES.value or role == "providers":
            user_table = "providers"
        elif role == User.PATIENT_USER.value:
            user_table = "patients"
        elif role == User.CAREGIVER_USER.value:
            user_table = "caregivers"
    if user_table:
        query = """ SELECT * FROM {user_table} WHERE internal_id = %s """.format(
            user_table=user_table
        )
        user = read_as_dict(cnx, query, (internal_id))
    else:
        for user_table in user_types:
            query = """ SELECT * FROM {user_table} WHERE internal_id = %s""".format(
                user_table=user_table
            )
            user = read_as_dict(cnx, query, (internal_id))
            if user:
                break
    return user[0] if user else None


def find_user_by_external_id(cnx, external_id, role=None):
    """
    Returns user data based on input external_id and role(optional)
    If role isnt passed then the function will search for user external_id
    in providers / caregivers / patients / customer_admins Tables
    """
    user_types = ["providers", "patients", "caregivers", "customer_admins"]
    user_table = None
    if role:
        if role in User.PROVIDER_ROLES.value or role == "providers":
            user_table = "providers"
        elif role == User.PATIENT_USER.value:
            user_table = "patients"
        elif role == User.CAREGIVER_USER.value:
            user_table = "caregivers"
        elif role == "customer_admin":
            user_table = "customer_admins"
    if user_table:
        query = """ SELECT * FROM {user_table} WHERE external_id = %s """.format(
            user_table=user_table
        )
        user = read_as_dict(cnx, query, (external_id))
    else:
        for user_table in user_types:
            query = """ SELECT * FROM {user_table} WHERE external_id = %s""".format(
                user_table=user_table
            )
            user = read_as_dict(cnx, query, (external_id))
            if user:
                break
    return user[0] if user else None


def get_user_org_ids(cnx, role, user_id=None, internal_id=None, external_id=None):
    """
    Get the org ids for patients, caregivers, providers.
    """
    user_columns = {
        "id": user_id,
        "internal_id": internal_id,
        "external_id": external_id,
    }
    if role in User.PROVIDER_ROLES.value or role == "providers":
        table = "providers"
        org_table = "provider_org"
        org_column = "providers_id"
    elif role == User.PATIENT_USER.value or role == "patients":
        table = "patients"
        org_column = "patients_id"
        org_table = "patient_org"
    else:
        table = "caregivers"
        org_column = "caregivers_id"
        org_table = "caregiver_org"
    for key in user_columns:
        if user_columns[key]:
            column_name = key
            column_value = user_columns[key]
            break
    query = """ SELECT DISTINCT organizations_id FROM
                {org_table} JOIN {table}
                ON {table}.id = {org_table}.{org_column}
                WHERE {table}.{column_name} = %s """.format(
        table=table, org_column=org_column, org_table=org_table, column_name=column_name
    )
    org_ids = read_query(cnx, query, (column_value))
    if org_ids:
        return [org[0] for org in org_ids]
    return []


def get_user_by_id(cnx, user_id, role):
    """
    Query the user in DB based on Role
    """
    if role in User.PROVIDER_ROLES.value or role == "provider":
        query = "SELECT * FROM providers WHERE id=%s"
    elif role == User.PATIENT_USER.value:
        query = "SELECT *, 'patient' as role FROM patients WHERE id=%s"
    elif role == User.CAREGIVER_USER.value:
        query = "SELECT *, 'caregiver' as role FROM caregivers WHERE id=%s"
    return read_as_dict(cnx, query, (user_id))


def admin_authorization(auth_function):
    """
    Returns Authorization decorator for Admin User
    """

    def decorator(*args, **kwargs):
        event = args[0]
        auth_user = event["requestContext"].get("authorizer")
        identity = event["requestContext"].get("identity")
        if auth_user.get("userRole") == "customer_admin":
            auth_user["ipv4"] = identity.get("sourceIp", "0.0.0.0")
            platform = event["headers"].get("sec-ch-ua-platform")
            auth_user["platform"] = platform.strip('"').upper() if platform else None
            return auth_function(*args, **kwargs)
        return {
            "statusCode": 400,
            "body": "User Not Authorized",
            "headers": get_headers(),
        }

    return decorator


def calculate_date_of_birth(born):
    """
    Returns age based on input DOB and current date
    """
    today = date.today()
    try:
        birthday = born.replace(year=today.year)
    except ValueError:
        # raised when birth date is February 29
        # and the current year is not a leap year
        birthday = born.replace(year=today.year, month=born.month + 1, day=1)
    if birthday > today:
        return today.year - born.year - 1
    return today.year - born.year


def get_org_name(cnx, org_ids):
    """
    Returns list if dict with the org id and name based in input org ids
    Return format:
    list of {"id": <org id>, "name": <org name>}
    """
    f_str = ",".join(["%s"] * len(org_ids))
    query = """ SELECT id, name FROM organizations WHERE id IN ({f_str}) """.format(
        f_str=f_str
    )
    return read_as_dict(cnx, query, tuple(org_ids))


def get_phi_data_from_internal_id(cnx, dynamodb, internal_id, role=None):
    """
    This Function:
    1. Gets user data based on input internal_id and role(optional)
    2. Extracts and returns phi_data for user based on external_id of user
    """
    user = find_user_by_internal_id(cnx, internal_id, role)
    if user:
        phi_data = get_phi_data(user["external_id"], dynamodb)
        return phi_data
    return


def get_s3_config(bucket_name, file_name, s3_client=None):
    """
    Returns S3 object data as JSON based on input file and s3 bucket name
    """
    if not s3_client:
        s3_client = boto3.client("s3", region_name=aws_region)
    logger.info("Retrieving file:%s from bucket:%s ", file_name, bucket_name)
    result = s3_client.get_object(Bucket=bucket_name, Key=file_name)
    logger.info("Data fetched from s3: " + str(result))
    data = result["Body"].read().decode()
    s3_config = json.loads(data)
    return s3_config


def decrypt(encrypted, key_object=None):
    """
    This Function:
    1. Gets Decryption key from AWS secret
    2. Encodes and converts the key to hash
    3. Uses the first 16 characters of the hash as the decryption key
    4. Decrypts input encrypted string using AES decryption cipher
    5. Returns decrypted string
    """
    try:
        if os.getenv("ENCRYPTION_KEY_SECRET_ID", None) is None:
            raise GeneralException("ENCRYPTION_KEY_SECRET_ID not set")
        else:
            if not key_object:
                key_object = get_secret_manager(os.getenv("ENCRYPTION_KEY_SECRET_ID"))
            if not key_object:
                raise GeneralException("key_object not present")
            key = hashlib.md5(
                key_object["chat_encrypt_decrypt_key"].encode("utf-8")
            ).hexdigest()[:16]

        def unpad(s):
            return s[: -ord(s[len(s) - 1 :])]

        enc = base64.urlsafe_b64decode(encrypted.encode("utf-8"))
        iv = enc[:16]
        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(enc[16:])).decode("utf-8")
    except GeneralException as e:
        logger.info(e)


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
        encrypt_key = get_secret_manager(os.getenv("ENCRYPTION_KEY_SECRET_ID"))
        if not encrypt_key:
            raise GeneralException("encrypt_key not present")
        key = hashlib.md5(
            encrypt_key["chat_encrypt_decrypt_key"].encode("utf-8")
        ).hexdigest()[:16]
    return key


def encrypt(plaintext):
    """
    This method is responsible to apply the AES encryption
    file and the Algorithm used is the AES
    """
    key = get_encryption_key()

    def pad(s):
        return s + (16 - len(s) % 16) * chr(16 - len(s) % 16)

    raw = pad(unidecode.unidecode(plaintext))
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(key.encode("utf8"), AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw.encode("utf-8"))).decode("utf-8")


def strip_dashes(phone_number: str):
    """
    This function strips and removes all instances of
    "-" from the input phone number
    """
    return phone_number.strip().replace("-", "")


def get_linked_patient_internal_ids(cnx, provider_internal_id):
    try:
        linked_patients = read_as_dict(
            cnx,
            GET_LINKED_PATIENTS_OF_PROVIDER,
            {"provider_internal_id": provider_internal_id},
        )
        pat_internal_ids = (
            [patient.get("pat_internal_id") for patient in linked_patients if patient]
            if linked_patients
            else []
        )
        return pat_internal_ids
    except pymysql.MySQLError as err:
        logger.exception(err)
    except Exception as err:
        logger.exception(err)
    return []


def check_user_access_for_patient_data(
    cnx, role: str, user_data: Union[dict, None], patient_internal_id
):
    is_allowed = False
    result = {}
    if role in ["physician", "nurse", "case_manager", "caregiver"] and user_data:
        pat_internal_ids = get_linked_patient_internal_ids(
            cnx, user_data["internal_id"]
        )
        if int(patient_internal_id) not in pat_internal_ids:
            is_allowed = False
            result = {"message": "The patient is not a part of the provider's network"}
        else:
            is_allowed = True
            result = {"message": "Success"}
    if role == "patient" and user_data:
        if str(patient_internal_id) != str(user_data["internal_id"]):
            is_allowed = False
            result = {
                "message": "You are not authorized to access another patient's data"
            }
        else:
            is_allowed = True
            result = {"message": "Success"}
    return is_allowed, result


def find_role_by_internal_id(cnx, internal_id):
    user_types = ["providers", "patients", "caregivers"]
    user_table = None
    role = None
    for user_table in user_types:
        query = """ SELECT * FROM {user_table} WHERE internal_id = %s""".format(
            user_table=user_table
        )
        user = read_as_dict(cnx, query, (internal_id))
        if user:
            if user_table == "providers":
                role = "provider"
            if user_table == "patients":
                role = "patient"
            if user_table == "caregivers":
                role = "caregiver"
            break
    return role


def find_role_by_external_id(cnx, external_id):
    user_types = ["providers", "patients", "caregivers", "customer_admins"]
    role = None
    for user_table in user_types:
        query = """ SELECT * FROM {user_table} WHERE external_id = %s""".format(
            user_table=user_table
        )
        user = read_as_dict(cnx, query, (external_id,))
        if user:
            if user_table == "providers":
                role = "provider"
            if user_table == "patients":
                role = "patient"
            if user_table == "caregivers":
                role = "caregiver"
            if user_table == "customer_admins":
                role = "customer_admin"
            break
    return role
