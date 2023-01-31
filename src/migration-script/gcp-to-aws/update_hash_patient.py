"""
alter table patients add hash_dob char(64) not null;
alter table patients add hash_fname char(64) not null;
alter table patients add hash_lname char(64) not null;
alter table patients add hash_ssn char(64) not null;
"""

import hashlib
import logging

import boto3
import pymysql
from botocore.exceptions import ClientError
from custom_exception import GeneralException
from db_ops import get_db_connect

cnx = get_db_connect()

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def chunks(lst, n):
    """Yield successive n-sized chunks from list."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def get_phi_data_list(external_ids, dynamodb=None):
    """
    Get the user PHI data based on external id/user sub
    :param partition key, dynamodb_instance
    :return: PHI data for User
    """
    external_id_in_chunks = chunks(external_ids, 100)
    items = []
    for external_ids in external_id_in_chunks:
        keys = [{"external_id": external_id} for external_id in external_ids]
        if not dynamodb:
            dynamodb = boto3.resource("dynamodb")
        try:
            response = dynamodb.batch_get_item(
                RequestItems={"user_pii": {"Keys": keys, "ConsistentRead": True}},
                ReturnConsumedCapacity="TOTAL",
            )
        except ClientError as e:
            logger.error(e.response["Error"]["Message"])
        else:
            items.extend(response["Responses"]["user_pii"])
    return items


def get_user_details(table):
    """
    Returns all external_id column values of the table passed as input
    """
    query = """SELECT external_id from {table} """.format(table=table)
    try:
        with cnx.cursor() as cursor:
            cursor.execute(query)
            return [row[0] for row in cursor.fetchall()]
    except pymysql.MySQLError as err:
        print(err)


def fetch_data_from_dynamo_db():
    """
    This function:
    1. Gets list of external_ids for all patients
    2. Gets and returns PHI data for all external_ids of patients
    """
    tables = ["patients"]
    ids = []
    for table in tables:
        ids.extend(get_user_details(table))
    users = get_phi_data_list(ids, dynamodb)
    return users


def create_hash_value(attr):
    """
    Creates and returns a sha256 hash string from input string
    """
    hash256 = hashlib.sha256(attr.encode())
    hashvalue = hash256.hexdigest()
    return hashvalue


def populate_hash_values_for_patient():
    """
    Adds hash values for FN, LN, DOB and SSN for the patient data in Table
    """
    users = fetch_data_from_dynamo_db()
    for user in users:
        try:
            external_id = user["external_id"]
            fname = user["first_name"].lower()
            lname = user["last_name"].lower()
            dob = user["dob"][0:10]
            ssn = user["ssn"]
            print(fname, lname, dob, ssn)
            hash_dob = create_hash_value(dob)
            hash_ssn = create_hash_value(ssn)
            hash_fname = create_hash_value(fname)
            hash_lname = create_hash_value(lname)
            print(hash_dob, hash_ssn, hash_fname, hash_lname)
            with cnx.cursor() as cursor:
                query = """ UPDATE patients
                            SET hash_dob = %s,
                                hash_ssn = %s,
                                hash_fname = %s,
                                hash_lname = %s
                            WHERE  external_id = %s """
                cursor.execute(
                    query, (hash_dob, hash_ssn, hash_fname, hash_lname, external_id)
                )
                cnx.commit()
        except GeneralException as err:
            logger.error(err)
    return "Patient Hash updated Successfully"


if __name__ == "__main__":
    populate_hash_values_for_patient()
