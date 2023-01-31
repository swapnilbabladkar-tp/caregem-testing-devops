import base64
import json
import logging
import os
import re
import secrets
import string
import unicodedata

import boto3
import pymysql
import requests
from botocore.exceptions import ClientError
from custom_exception import GeneralException
from db_ops import get_db_connect
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

dynamo_db = boto3.resource("dynamodb", region_name="us-east-1")
client = boto3.client("cognito-idp", region_name="us-east-1")

user_pool_id = os.getenv("USER_POOL_ID")

api_key = os.getenv("TRUEVAULT_API_KEY")

aws_region = "us-east-1"

keys = [
    "last_name",
    "home_tel",
    "group_name",
    "drive_license_number",
    "home_addr_2",
    "home_addr_1",
    "year_grad_med_school",
    "first_name",
    "external_id_old",
    "cell",
    "state",
    "role",
    "email",
    "npi",
    "degree",
    "specialty",
    "ssn",
    "dea_number",
    "address_zip",
    "office_addr_2",
    "address_city",
    "office_addr_1",
    "dob",
    "gender",
    "nursing_license_number",
    "office_tel",
]

_TRUEVAULT_URL = "https://api.truevault.com/v1"


def read_as_dict(connection, query, params=None):
    """
    Execute a select query and return the outcome as a dict
    """
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            if params:
                cursor.execute(query, (params))
            else:
                cursor.execute(query)
            return cursor.fetchall()
    except pymysql.MySQLError as err:
        logger.error(err)


def _auth_headers(content_type=None):
    """
    Custom header for fetching user data from Truevault
    """
    headers = {"Authorization": "Basic %s" % (api_key)}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _post(url, data):
    """
    POST method for fetching user data from Truevault
    """
    res = requests.post(
        url,
        data=data,
        headers=_auth_headers(content_type="application/x-www-form-urlencoded"),
        timeout=15,
    )
    return res


def search_users_by_id(ids, full=True):
    """
    Function to search user data in truevault with list of ids as input
    """
    criteria = {}
    search_option = {
        "filter": {"$tv.id": {"type": "in", "value": ids}},
        "per_page": 1000,
        "full_document": full,
    }
    criteria["search_option"] = base64.b64encode(
        json.dumps(search_option).encode("utf-8")
    )
    response = _post("%s/users/search" % (_TRUEVAULT_URL), criteria)
    data = response.json().get("data", {})
    if "documents" in data and data["documents"] is not None:
        documents = data["documents"]
        users = {}
        for document in documents:
            users.update(
                {
                    document["user_id"]: json.loads(
                        base64.b64decode(document["attributes"])
                    )
                }
            )

    return users


def check_username_exists(uname):
    """
    Check for the user name in cognito.
    """
    try:
        user_info = client.admin_get_user(UserPoolId=user_pool_id, Username=uname)
        auth_resp = {"username": user_info.get("Username")}
        auth_resp.update(
            {
                attr.get("Name"): attr.get("Value")
                for attr in user_info.get("UserAttributes")
            }
        )
        return auth_resp
    except client.exceptions.UserNotFoundException:
        return None


def filter_chars(chars):
    """
    Cleans up the input string with following steps
    1. Normalizes and encodes the string
    2. Decodes the string
    3. Removes non alplhanumeric characters from string
    """
    chars = unicodedata.normalize("NFKD", chars).encode("ascii", "ignore")
    chars = chars.decode("utf-8")
    return "".join(e for e in chars if e.isalnum())


def get_user_name(fname, lname):
    """
    Generate Username
    1.Get the first letter of first name.
    2.Get the first 7 letter of last name.
    3.Add suffix in case of duplicates.
    """
    fname = filter_chars(fname)[0]
    lname = filter_chars(lname)[0:7]
    username = fname + lname
    username = username.lower()
    while check_username_exists(username):
        check_username_exists(username)
        try:
            suffix = int(re.search(r"\d+", username).group())
            username = re.sub(r"\d+", "", username) + str(suffix + 1)
        except AttributeError:
            username = username + str("1")
        except ClientError as e:
            print(e)
    return username


def generate_cognito_password():
    """
    Generate a random 9 digit password
    """
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for i in range(5))
    password = "Pa1" + password + "!"
    return password


def add_users_to_cognito(uname, email, name, portal_type=None):
    """
    Add user in cognito with username and email as input and a temporary password
    """
    try:
        resp = client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=uname,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "profile", "Value": "none"},
                {"Name": "email_verified", "Value": "true"},
            ],
            MessageAction="SUPPRESS",
            TemporaryPassword=generate_cognito_password(),
            DesiredDeliveryMediums=["EMAIL"],
            ClientMetadata={"name": name, "org": "", "portal": portal_type},
        )
        cogito_user = {"username": resp["User"].get("Username")}
        cogito_user.update(
            {
                attr.get("Name"): attr.get("Value")
                for attr in resp["User"].get("Attributes")
            }
        )
        # client.admin_add_user_to_group(UserPoolId=user_pool_id, Username=uname, GroupName=grp_name)
        return cogito_user
    except GeneralException as e:
        logger.info("Error while Adding User to cognito")

        logger.error(e)


def user_fields(user, user_info, user_type):
    """
    Formats input user_info into required format based on user_type passed as input
    """
    if user_type in ("patients", "caregivers"):
        upd_info = {
            "address_city": user_info["address_city"],
            "address_zip": user_info["address_zip"],
            "home_addr_1": user_info["home_addr_1"] or "",
            "home_addr_2": user_info.get("home_addr_2") or "",
            "state": user_info["state"],
            "cell": user_info["cell"],
            "home_tel": user_info["home_tel"],
            "first_name": user_info["first_name"].strip(),
            "last_name": user_info["last_name"].strip(),
            "username": get_user_name(
                user_info["first_name"].strip(), user_info["last_name"].strip()
            ),
            "dob": user_info["dob"][0:10] if user_info.get("dob") else "",
            "role": user_type[:-1],
            "email": user_info["email"],
            "gender": user_info["gender"],
            "drive_license_number": user_info.get("drive_license_number") or "",
            "cell_country_code": "+1",
            "home_tel_country_code": "+1",
        }
        if user_type == "patients":
            upd_info.update(
                {"ssn": user_info["ssn"] if user_info.get("ssn") else "1111"}
            )
            upd_info.update(
                {
                    "middle_name": user_info["middle_name"]
                    if user_info.get("middle_name")
                    else ""
                }
            )
    elif user_type == "providers":
        upd_info = {
            "address_city": user_info["address_city"],
            "address_zip": user_info["address_zip"],
            "office_addr_1": user_info["office_addr_1"] or "",
            "office_addr_2": user_info.get("office_addr_2") or "",
            "state": user_info["state"],
            "dob": user_info["dob"][0:10] if user_info.get("dob") else "",
            "cell": user_info["cell"],
            "office_tel": user_info["office_tel"],
            "year_grad_med_school": user_info.get("year_grad_med_school") or "",
            "first_name": user_info["first_name"].strip(),
            "last_name": user_info["last_name"].strip(),
            "username": get_user_name(
                user_info["first_name"].strip(), user_info["last_name"].strip()
            ),
            "npi": user_info.get("npi") or "",
            "role": user_info["role"],
            "email": user_info["email"],
            "drive_license_number": user_info.get("drive_license_number") or "",
            "cell_country_code": "+1",
            "office_tel_country_code": "+1",
        }
        if "nursing_license_number" in user_info:
            upd_info.update(
                {
                    "nursing_license_number": user_info.get("nursing_license_number")
                    or ""
                }
            )
        if "dea_number" in user_info:
            upd_info.update({"dea_number": user_info.get("dea_number") or ""})
    return upd_info


def get_user_details_from_db(cnx, table):
    """
    Returns all rows of the table passed as input
    """
    query = """ SELECT * FROM {table} """.format(table=table)
    user_details = read_as_dict(cnx, query)
    return user_details


def update_external_id(cnx, table, external_id, id):
    """
    Updates external_id with new value for table name in input
    """
    query = """ UPDATE {table} SET external_id = %s WHERE id =%s """.format(table=table)
    try:
        with cnx.cursor() as cursor:
            cursor.execute(query, (external_id, id))
            cnx.commit()
    except pymysql.MySQLError as err:
        print(err)


def migrate_providers_patients_caregivers():
    """
    This Function:
    1. Gets All Providers, Patients, Caregiver User details from SQL table
    2. Gets user data from Truevault
    3. Adds each user in list to Cognito
    4. Updates external_id for user in SQL table
    5. Formats user data from Truevault and inserts to Dynamodb
    """
    user_tables = [
        ("patients", "patient_org"),
        ("providers", "provider_org"),
        ("caregivers", "caregiver_org"),
    ]
    final_result = []
    user_pii = dynamo_db.Table("user_pii")
    cnx = get_db_connect()
    for table in user_tables:
        user_details = get_user_details_from_db(cnx, table[0])
        external_ids = []
        for user in user_details:
            external_ids.append(user["external_id"])
        tv_data = search_users_by_id(external_ids)
        for user in user_details:
            try:
                user_info = tv_data[user["external_id"]]
                user_info = user_fields(user, user_info, table[0])
                name = user_info["first_name"] + " " + user_info["last_name"]
                cognito_user = add_users_to_cognito(
                    user_info["username"], user_info["email"], name, "WebApp"
                )
                update_external_id(cnx, table[0], cognito_user["sub"], user["id"])
                user_info["external_id"] = cognito_user["sub"]
                user_pii.put_item(Item=user_info)
                final_result.append(user_info)
                print(user_info)
            except GeneralException as e:
                print("============Error==========")
                print(e)
                print("============Error==========")
    return final_result


def migrate_customer_admins():
    """
    This Function:
    1. Gets All Customer Admin User details from SQL table
    2. Gets user data from Truevault
    3. Adds each user in list to Cognito
    4. Updates external_id for user in SQL table
    5. Formats user data from Truevault and inserts to Dynamodb
    """
    cnx = get_db_connect()
    user_details = get_user_details_from_db(cnx, "customer_admins")
    external_ids = []
    final_result = []
    user_pii = dynamo_db.Table("user_pii")
    for user in user_details:
        external_ids.append(user["external_id"])
    tv_data = search_users_by_id(external_ids)
    for user in user_details:
        try:
            user_info = tv_data[user["external_id"]]
            user_info = {
                "username": get_user_name(
                    user_info["first_name"].strip(), user_info["last_name"].strip()
                ),
                "first_name": user_info["first_name"].strip(),
                "last_name": user_info["last_name"].strip(),
                "dob": user_info["dob"][0:10] if user_info.get("dob") else "",
                "org_id": user_info.get("org_id"),
                "role": user_info.get("role") or "customer_admin",
                "address_city": user_info.get("city") or "",
                "state": user_info.get("state"),
                "office_addr_1": user_info.get("address_1") or "",
                "office_addr_2": user_info.get("address_2") or "",
                "office_tel": user_info.get("phone_number") or "",
                "cell": user_info.get("cell") or "",
                "address_zip": user_info.get("zipcode") or "",
                "email": user_info["email"],
                "drive_license_number": user_info.get("drive_license") or "",
                "gender": user_info.get("sex") or "",
                "cell_country_code": "+1",
                "office_tel_country_code": "+1",
            }
            name = user_info["first_name"] + " " + user_info["last_name"]
            cognito_user = add_users_to_cognito(
                user_info["username"], user_info["email"], name, "Admin"
            )
            update_external_id(cnx, "customer_admins", cognito_user["sub"], user["id"])
            user_info["external_id"] = cognito_user["sub"]
            user_pii.put_item(Item=user_info)
            print(user_info)
            final_result.append(user_info)
        except GeneralException as e:
            print("============Error==========")
            print(e)
            print("============Error==========")
    return final_result


def main():
    """
    Main Function that migrates All user data from Truevault
    """
    final_result = []
    final_result.extend(migrate_providers_patients_caregivers())
    final_result.extend(migrate_customer_admins())
    return final_result
