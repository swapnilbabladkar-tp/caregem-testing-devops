import hashlib
import logging
import os
import secrets
import string
from datetime import datetime, timedelta

import boto3
import pymysql
import pytz
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
from custom_exception import GeneralException
from shared import get_user_org_ids, strip_dashes
from sqls.user import (
    DELETE_NETWORK,
    GENERATE_INTERNAL_ID,
    GET_ORG_DETAILS,
    INSERT_USER_ORG,
    NETWORK_USER_BY_PATIENT_ID,
    NETWORK_USER_BY_USER_ID,
)

aws_region = os.getenv("AWSREGION")
user_pool_id = os.getenv("USER_POOL_ID")

cognito_client = boto3.client("cognito-idp", region_name=aws_region)
dynamodb = boto3.resource("dynamodb", region_name=aws_region)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

profile_table = os.getenv("USER_PROFILE_TABLE_NAME")


def execute_query(cnx, query, params=None, fetchone=None):
    """
    Execute a select query and return the outcome as a dict
    """
    try:
        with cnx.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query, params) if params else cursor.execute(query)
            result = cursor.fetchone() if fetchone else cursor.fetchall()
            cnx.commit()
            return result if result else {}
    except pymysql.MySQLError as err:
        logger.exception(err)
        return {}


def save_db_instance(cnx, query, params):
    """
    Function to read data from SQL Tables
    """
    try:
        with cnx.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
        cnx.commit()
        return True
    except pymysql.MySQLError as err:
        logger.error(err)


def generate_cognito_password():
    """
    Generate a random 9 digit password
    """
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for i in range(7))
    password = "Pa1" + password + "@"
    return password


def create_user_in_cognito(uname, email, name, org_name, portal_type=None):
    """
    This Function:
    1. Adds user in cognito with username and email as input
       and a temporary password
    2. Sends Welcome email to the added user
    """
    if not portal_type:
        portal_type = "Org"
    try:
        resp = cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=uname,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "profile", "Value": "none"},
                {"Name": "email_verified", "Value": "true"},
            ],
            TemporaryPassword=generate_cognito_password(),
            DesiredDeliveryMediums=["EMAIL"],
            ClientMetadata={"name": name, "org": org_name, "portal": portal_type},
        )
        cogito_user = {"username": resp["User"].get("Username")}
        cogito_user.update(
            {
                attr.get("Name"): attr.get("Value")
                for attr in resp["User"].get("Attributes")
            }
        )
        return 200, cogito_user
        # client.admin_add_user_to_group(UserPoolId=user_pool_id, Username=uname, GroupName=role)
    except cognito_client.exceptions.UsernameExistsException as err:
        logger.error(err)
        return 106, "Username Already exists"
    except cognito_client.exceptions.InvalidParameterException as err:
        logger.error(err)
        return 106, "Invalid email address format"
    except cognito_client.exceptions.CodeDeliveryFailureException as err:
        logger.error(err)
        return 106, "Invalid email address format"
    except GeneralException as err:
        logger.error(err)
        raise err


def check_username_exists(uname):
    """
    Check for the username in cognito.
    """
    try:
        user_info = cognito_client.admin_get_user(
            UserPoolId=user_pool_id, Username=uname
        )
        auth_resp = {"username": user_info.get("Username")}
        auth_resp.update(
            {
                attr.get("Name"): attr.get("Value")
                for attr in user_info.get("UserAttributes")
            }
        )
        return auth_resp
    except cognito_client.exceptions.UserNotFoundException as err:
        logger.info(err)
        return None


def remove_user(cognito=None, dynamo=None):
    """
    Delete the user from cognito as well as dyanamo db.
    """
    try:
        table = dynamodb.Table(profile_table)
        if cognito:
            cognito_client.admin_delete_user(
                UserPoolId=user_pool_id, Username=cognito["username"]
            )
        if dynamo:
            table.delete_item(Key={"external_id": dynamo["external_id"]})
        return True
    except ClientError as err:
        logger.error(err.response["Error"]["Message"])


def get_user_details_from_cognito(uname):
    """Get User details from cognito"""
    try:
        response = cognito_client.admin_get_user(
            UserPoolId=user_pool_id, Username=uname
        )
        user_attr = response["UserAttributes"]
        user = {}
        for attr in user_attr:
            user[attr["Name"]] = attr["Value"]
        return user
    except ClientError as err:
        logging.error(err)


def check_diff_instance(new_user, existing_user, user_type=None):
    """
    Check the New username, ssn, dob
    """
    if user_type == "patients":
        same_name_dob_ssn = (
            existing_user["dob"] != new_user["dob"]
            or existing_user["first_name"] != new_user["first_name"]
            or existing_user["last_name"] != new_user["last_name"]
            or existing_user["ssn"] != new_user["ssn"]
        )
        return same_name_dob_ssn
    same_name_dob_email = (
        existing_user["dob"] != new_user["dob"]
        or existing_user["first_name"] != new_user["first_name"]
        or existing_user["last_name"] != new_user["last_name"]
        or existing_user["email"] != new_user["email"]
    )
    return same_name_dob_email


def create_hash_value(arg1, arg2, arg3=None):
    """
    Returns hash string based in input arguments
    """
    if arg3:
        hash_string = f"{arg1}|{arg2}|{arg3}"
    else:
        hash_string = f"{arg1}|{arg2}"
    hash256 = hashlib.sha256(hash_string.encode())
    hash_value = hash256.hexdigest()
    return hash_value


def format_customer_admin_fields(input_profile_data, user_info):
    profile_data = input_profile_data
    profile_keys = [
        "username",
        "first_name",
        "last_name",
        "dob",
        "org_id",
        "role",
        "address_city",
        "state",
        "office_addr_1",
        "office_addr_2",
        "office_tel",
        "cell",
        "address_zip",
        "email",
        "drive_license_number",
        "gender",
        "office_tel_country_code",
        "cell_country_code",
    ]
    for key in profile_keys:
        profile_data.update({key: user_info.get(key) or ""})
    if "cell" in user_info:
        profile_data.update({"cell": strip_dashes(user_info.get("cell", ""))})
    if "office_tel" in user_info:
        profile_data.update(
            {"office_tel": strip_dashes(user_info.get("office_tel", ""))}
        )
    if "cell_country_code" in user_info:
        profile_data.update(
            {"cell_country_code": user_info.get("cell_country_code", "+1")}
        )
    if "office_tel_country_code" in user_info:
        profile_data.update(
            {"office_tel_country_code": user_info.get("office_tel_country_code", "+1")}
        )
    return profile_data


def format_patient_caregiver_fields(input_profile_data, user_info):
    profile_data = input_profile_data
    profile_keys = [
        "address_city",
        "address_zip",
        "middle_name",
        "cell_country_code",
        "home_tel_country_code",
        "home_addr_1",
        "home_addr_2",
        "state",
        "cell",
        "home_tel",
        "first_name",
        "last_name",
        "role",
        "email",
        "gender",
        "drive_license_number",
        "external_id",
        "username",
    ]
    for key in profile_keys:
        profile_data.update({key: user_info.get(key, "")})
    if "dob" in user_info:
        profile_data.update({"dob": user_info.get("dob", "")})
    if "ssn" in user_info:
        profile_data.update({"ssn": user_info.get("ssn", "")})
    if "middle_name" in user_info:
        profile_data.update({"middle_name": user_info.get("middle_name", "")})
    if "cell" in user_info:
        profile_data.update({"cell": strip_dashes(user_info.get("cell", ""))})
    if "home_tel" in user_info:
        profile_data.update({"home_tel": strip_dashes(user_info.get("home_tel", ""))})
    if "cell_country_code" in user_info:
        profile_data.update(
            {"cell_country_code": user_info.get("cell_country_code", "+1")}
        )
    if "home_tel_country_code" in user_info:
        profile_data.update(
            {"home_tel_country_code": user_info.get("home_tel_country_code", "+1")}
        )
    return profile_data


def format_provider_fields(input_profile_data, user_info):
    profile_data = input_profile_data
    profile_keys = [
        "address_city",
        "address_zip",
        "cell_country_code",
        "office_tel_country_code",
        "office_addr_1",
        "office_addr_2",
        "state",
        "cell",
        "office_tel",
        "year_grad_med_school",
        "first_name",
        "last_name",
        "npi",
        "role",
        "dob",
        "email",
        "drive_license_number",
        "external_id",
        "username",
    ]

    for key in profile_keys:
        profile_data.update({key: user_info.get(key) or ""})
    if "nursing_license_number" in user_info:
        profile_data.update(
            {"nursing_license_number": user_info.get("nursing_license_number", "")}
        )
    if "dea_number" in user_info:
        profile_data.update({"dea_number": user_info.get("dea_number", "")})
    if "cell" in user_info:
        profile_data.update({"cell": strip_dashes(user_info.get("cell", ""))})
    if "office_tel" in user_info:
        profile_data.update(
            {"office_tel": strip_dashes(user_info.get("office_tel", ""))}
        )
    if "cell_country_code" in user_info:
        profile_data.update(
            {"cell_country_code": user_info.get("cell_country_code", "+1")}
        )
    if "office_tel_country_code" in user_info:
        profile_data.update(
            {"office_tel_country_code": user_info.get("office_tel_country_code", "+1")}
        )
    return profile_data


def format_user_fields(user_info, user_type):
    """
    Formats and returns input dict to required format based on input user_type
    """
    profile_data = {}
    if user_type == "customer_admin":
        profile_data = format_customer_admin_fields(
            input_profile_data=profile_data, user_info=user_info
        )
    if user_type in ("patients", "caregivers"):
        profile_data = format_patient_caregiver_fields(
            input_profile_data=profile_data, user_info=user_info
        )
    elif user_type == "providers":
        profile_data = format_provider_fields(
            input_profile_data=profile_data, user_info=user_info
        )
    return profile_data


def get_user_via_email(email, role):
    """
    Scans the Entire user_phi table to get the Email
    """
    try:
        table = dynamodb.Table(profile_table)
        user_phi = table.scan(
            FilterExpression=Attr("email").eq(email) & Attr("role").eq(role)
        )
        return user_phi.get("Items")
    except ClientError as err:
        logger.error(err)


def update_email_in_cognito(uname, email, portal_type):
    """
    Update Email attribute for input username in cognito
    """
    try:
        response = cognito_client.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=uname,
            UserAttributes=[{"Name": "email", "Value": email}],
            ClientMetadata={"portal": portal_type},
        )
        return response["ResponseMetadata"]["HTTPStatusCode"]
    except ClientError as err:
        logger.error(err)
        return None


def create_update_user_profile(user_data):
    """
    Add the User Details to Dynamo db.
    """
    try:
        table = dynamodb.Table(profile_table)
        table.put_item(Item=user_data)
        response = table.get_item(Key={"external_id": user_data["external_id"]})
        return response["Item"]
    except ClientError as err:
        logger.error(err)
        return None


def state_conversion(input_state):
    """
    This function converts input state name to the short syntax
    """
    us_state_abbrev = {
        "Alabama": "AL",
        "Alaska": "AK",
        "American Samoa": "AS",
        "Arizona": "AZ",
        "Arkansas": "AR",
        "California": "CA",
        "Colorado": "CO",
        "Connecticut": "CT",
        "Delaware": "DE",
        "District of Columbia": "DC",
        "Florida": "FL",
        "Georgia": "GA",
        "Guam": "GU",
        "Hawaii": "HI",
        "Idaho": "ID",
        "Illinois": "IL",
        "Indiana": "IN",
        "Iowa": "IA",
        "Kansas": "KS",
        "Kentucky": "KY",
        "Louisiana": "LA",
        "Maine": "ME",
        "Maryland": "MD",
        "Massachusetts": "MA",
        "Michigan": "MI",
        "Minnesota": "MN",
        "Mississippi": "MS",
        "Missouri": "MO",
        "Montana": "MT",
        "Nebraska": "NE",
        "Nevada": "NV",
        "New Hampshire": "NH",
        "New Jersey": "NJ",
        "New Mexico": "NM",
        "New York": "NY",
        "North Carolina": "NC",
        "North Dakota": "ND",
        "Northern Mariana Islands": "MP",
        "Ohio": "OH",
        "Oklahoma": "OK",
        "Oregon": "OR",
        "Pennsylvania": "PA",
        "Puerto Rico": "PR",
        "Rhode Island": "RI",
        "South Carolina": "SC",
        "South Dakota": "SD",
        "Tennessee": "TN",
        "Texas": "TX",
        "Utah": "UT",
        "Vermont": "VT",
        "Virgin Islands": "VI",
        "Virginia": "VA",
        "Washington": "WA",
        "West Virginia": "WV",
        "Wisconsin": "WI",
        "Wyoming": "WY",
    }
    abbrev_us_state = dict(map(reversed, us_state_abbrev.items()))

    if len(input_state) == 2:
        new_state = abbrev_us_state[input_state]
    else:
        new_state = us_state_abbrev[input_state]

    return new_state


def str_dob_to_full_date(dob):
    """
    Converts input DOB to required date string
    1. Converts datetime to string
    2. For yyyymmdd format, converts to required format with 12pm as time
    3. For yyyy/mm/dd format, converts to required format with 12pm as time
    4. For yyyy-mm-dd format, converts to required format with 12pm as time
    """
    date_dob = dob
    if isinstance(dob, datetime):
        date_dob = (pytz.utc.localize(dob) + timedelta(hours=12)).strftime(
            "%m-%d-%Y %H:%M:%S %Z"
        )
    elif isinstance(dob, str):
        if len(dob) == 8:
            date_dob = (
                pytz.utc.localize(datetime.strptime(dob, "%Y%m%d"))
                + timedelta(hours=12)
            ).strftime("%m-%d-%Y %H:%M:%S %Z")
        if "/" in dob:
            date_dob = (
                pytz.utc.localize(datetime.strptime(dob, "%m/%d/%Y"))
                + timedelta(hours=12)
            ).strftime("%m-%d-%Y %H:%M:%S %Z")
        date_dob = (
            pytz.utc.localize(datetime.strptime(dob, "%m-%d-%Y")) + timedelta(hours=12)
        ).strftime("%m-%d-%Y %H:%M:%S %Z")
    return date_dob


def get_user_exception(exception_id):
    """
    Add the User Details to Dynamo db.
    """
    try:
        table = dynamodb.Table("user_exceptions")
        logger.info("GeneralException Id %s", exception_id)
        response = table.get_item(Key={"exception_id": exception_id})
        return response["Item"]
    except ClientError as err:
        logger.error(err)
        return None


def add_to_user_exception(user_data):
    """
    Add the User Details to Dynamo db.
    """
    try:
        table = dynamodb.Table("user_exceptions")
        table.put_item(Item=user_data)
        response = table.get_item(Key={"exception_id": user_data["exception_id"]})
        return response["Item"]
    except ClientError as err:
        logger.error(err)
        return None


def get_next_sequence(cnx):
    """
    Returns the next from id_sequence Table to be used as internal id.
    """
    try:
        with cnx.cursor() as cursor:
            cursor.execute(GENERATE_INTERNAL_ID)
            cnx.commit()
        return cursor.lastrowid
    except pymysql.MySQLError as err:
        logger.error(err)


def get_org_name(cnx, org_id):
    """
    Returns Org ID and Name for input org id
    """
    return execute_query(cnx, GET_ORG_DETAILS, {"org_id": org_id}, fetchone=True)


# def get_customer_admin(cnx, idn):
#     query = """ SELECT id,
#                        external_id,
#                        name,
#                        _organization_id AS org_id,
#                     is_read_only
#                 FROM customer_admins WHERE id = %(id)s """
#     phi_data = get_phi_data(customer_admin["external_id"], dynamodb)
#     customer_admin.update(phi_data)
#     return execute_query(cnx, query, {"id": idn}, fetchone=True)


def get_org_table_column(role):
    """
    Returns dict with table, org_table and org_column as keys based on role
    """
    response = None
    if role in ["physician", "nurse", "case_manager", "providers"]:
        response = {
            "table": "providers",
            "org_table": "provider_org",
            "org_column": "providers_id",
        }
    elif role == "patient":
        response = {
            "table": "patients",
            "org_table": "patient_org",
            "org_column": "patients_id",
        }
    elif role == "caregiver":
        response = {
            "table": "caregivers",
            "org_table": "caregiver_org",
            "org_column": "caregivers_id",
        }
    return response


def insert_user_org_query(role):
    """
    Returns complete query for inserting data for
    provider_org/patient_org/caregiver_org based on role
    """
    resp = get_org_table_column(role)
    return INSERT_USER_ORG.format(
        org_table=resp["org_table"], org_column=resp["org_column"]
    )


def link_user_to_new_org(cnx, user, role, org_id):
    """
    Links selected user to a org id
    """
    insert_user_org = insert_user_org_query(role)
    if save_db_instance(cnx, insert_user_org, {"org_id": org_id, "id": user["id"]}):
        return "User Linked Successfully"


def _execute_network_fixes(cnx, user_internal_id=None, patient_id=None):
    """
    Update Caregiver / Provider Network data (Unused function)
    """
    connected_user_entries = []
    network_to_be_deleted = []
    try:
        if user_internal_id:
            connected_user_entries.extend(
                execute_query(
                    cnx, NETWORK_USER_BY_USER_ID, {"user_id": user_internal_id}
                )
            )
        else:
            connected_user_entries.extend(
                execute_query(
                    cnx, NETWORK_USER_BY_PATIENT_ID, {"patient_id": patient_id}
                )
            )

        for user_entry in connected_user_entries:
            user_still_connected = False
            if user_entry["user_type"] == "caregiver":
                user_orgs = get_user_org_ids(
                    cnx, "caregiver", internal_id=user_entry["user_internal_id"]
                )
            else:
                user_orgs = get_user_org_ids(
                    cnx, "providers", internal_id=user_entry["user_internal_id"]
                )
            patient_orgs = get_user_org_ids(
                cnx, "patient", user_id=user_entry["_patient_id"]
            )
            logger.info(f"patient orgs:: {patient_orgs} user orgs:: {user_orgs}")
            if set(user_orgs) & set(patient_orgs):
                user_still_connected = True

            if not user_still_connected:
                network_to_be_deleted.append(user_entry["id"])
        if network_to_be_deleted:
            logger.info("Executing Network fixes for the ids %s", network_to_be_deleted)
            with cnx.cursor() as cursor:
                cursor.execute(DELETE_NETWORK, {"ids": tuple(network_to_be_deleted)})
                cnx.commit()
    except pymysql.MySQLError as err:
        logger.error(err)


def get_hash_value(attr: str) -> str:
    """Create a hash value in sha256 and returns it"""
    hash256 = hashlib.sha256(attr.encode())
    return hash256.hexdigest()
