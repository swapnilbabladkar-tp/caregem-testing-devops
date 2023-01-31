import logging
import os

import boto3
import pymysql
from custom_exception import GeneralException
from email_template import UserLockedEmail, send_mail_to_user
from shared import get_db_connect, get_phi_data, read_as_dict

dynamodb = boto3.resource("dynamodb")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()

max_login_attempts = int(os.getenv("MAX_LOGIN_ATTEMPTS"))


def add_user_to_lock_table(cnx, external_id):
    """
    Add Entry for User external id in the locked_user Table
    """
    try:
        with cnx.cursor() as cursor:
            cursor.execute(
                "INSERT INTO locked_user (external_id) VALUES (%(external_id)s)",
                {"external_id": external_id},
            )
            logger.info("Added entry to lock table %s", external_id)
            cnx.commit()
    except pymysql.MySQLError as err:
        logging.error(err)


def is_user_locked(cnx, external_id, email):
    """
    This Function:
    1. Get Login Attempt data for user external id
    2. If data doesnt exist then adds user to table
    3. Checks if attempts > max_login_attempts
    4. If True, Prevents login and sends email to user
    5, If False, Increases login attempt count by 1 for the user
    """
    query = """SELECT * FROM locked_user WHERE external_id = %(external_id)s"""
    result = read_as_dict(cnx, query, {"external_id": external_id}, fetchone=True)
    if not result:
        add_user_to_lock_table(cnx, external_id)
        return False
    if result["attempts"] > max_login_attempts:
        logger.info("User is locked need reset from backend")
        phi_data = get_phi_data(external_id, dynamodb)
        user_locked_email = UserLockedEmail(
            phi_data.get("first_name", "User") if phi_data else "User",
            result["attempts"] + 1,
        )
        send_mail_to_user([email], user_locked_email)
        return bool(result)
    try:
        with cnx.cursor() as cursor:
            attempts = result["attempts"] + 1
            query = """ UPDATE locked_user
                        SET    locked_user.attempts = %(attempts)s
                        WHERE  locked_user.id = %(id)s"""
            cursor.execute(query, {"attempts": attempts, "id": result["id"]})
            cnx.commit()
            return False
    except pymysql.MySQLError as err:
        logging.error(err)
        raise err


def lambda_handler(event, context):
    """
    Lambda Handler for Pre Auth Trigger Lambda in Cognito
    """
    user_attr = event["request"]["userAttributes"]
    if event["triggerSource"] == "PreAuthentication_Authentication":
        if is_user_locked(connection, user_attr["sub"], user_attr["email"]):
            raise GeneralException("User is locked")
    return event
