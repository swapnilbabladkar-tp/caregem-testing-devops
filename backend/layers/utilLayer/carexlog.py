import logging
from datetime import datetime

from custom_exception import GeneralException

LOG_APP_TAG = "CARELOGIG_LOG"

ADD_NEW_CUSTOMER_ADMIN = "ADD_NEW_CUSTOMER_ADMIN"
ADD_NEW_ORG = "ADD_NEW_ORG"
CHANGE_CUSTOMER_ADMIN_INFO = "CHANGE_CUSTOMER_ADMIN_INFO"
CHANGE_ORG_INFO = "CHANGE_ORG_INFO"
READ_CUSTOMER_ADMIN_INFO = "READ_CUSTOMER_ADMIN_INFO"
READ_ORG_INFO = "READ_ORG_INFO"
REMOVE_CUSTOMER_ADMIN = "REMOVE_CUSTOMER_ADMIN"
RESTORE_USERS = "RESTORE_USERS"
ADD_NEW_USER = "ADD_NEW_USER"
ARCHIVE_USER = "ARCHIVE_USER"
CHANGE_NETWORK = "CHANGE_NETWORK"
CHANGE_USER_INFO = "CHANGE_USER_INFO"
LOGIN_ATTEMPT = "LOGIN_ATTEMPT"
PASSWORD_RESET = "PASSWORD_RESET"
MESSAGE = "MESSAGE"
MESSAGE_HISTORY = "MESSAGE_HISTORY"
READ_USER_CHAT = "READ_USER_CHAT"
READ_PATIENT_INFO = "READ_PATIENT_INFO"
READ_USER_INFO = "READ_USER_INFO"
UNARCHIVE_USER = "UNARCHIVE_USER"
READ_USER_CHANGES_LOG = "READ_USER_CHANGES_LOG"

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"

LOG_INFO = "INFO"
LOG_ERROR = "ERROR"
LOG_WARN = "WARN"
LOG_DEBUG = "DEBUG"


def audit_info(
    cnx, action, status=STATUS_SUCCESS, auth_user=None, target_user=None, message=None
):
    """
    Inserts activity log with log_type as INFO
    """
    _db_logging(cnx, LOG_INFO, action, status, auth_user, target_user, message)


def audit_debug(
    cnx, action, status=STATUS_SUCCESS, auth_user=None, target_user=None, message=None
):
    """
    Inserts activity log with log_type as DEBUG
    """
    _db_logging(cnx, LOG_DEBUG, action, status, auth_user, target_user, message)


def audit_warning(
    cnx, action, status=STATUS_SUCCESS, auth_user=None, target_user=None, message=None
):
    """
    Inserts activity log with log_type as WARNING
    """
    _db_logging(cnx, LOG_WARN, action, status, auth_user, target_user, message)


def audit_error(
    cnx, action, status=STATUS_SUCCESS, auth_user=None, target_user=None, message=None
):
    """
    Inserts activity log with log_type as ERROR
    """
    _db_logging(cnx, LOG_ERROR, action, status, auth_user, target_user, message)


def _db_logging(cnx, log_type, action, status, auth_user, target_user, message):
    """
    Inserts row in activity_log based on input data
    """
    try:
        utc_timestamp = datetime.utcnow()
        if auth_user:
            auth_email = auth_user.get("email", None)
            auth_id = auth_user.get("id", None)
            auth_org = auth_user.get("userOrg", None)
            auth_role = auth_user.get("userRole", None)
            auth_platform = auth_user.get("platform", "MOBILE")
            auth_ipv4 = auth_user.get("ipv4", None)

            if len(auth_ipv4) > 15:
                message = "[IPv6 {}] {}".format(auth_ipv4, message)
                auth_ipv4 = "0.0.0.0"
        if target_user:
            target_id = target_user.get("id", None)
            target_role = target_user.get("role", None)

        query = """ INSERT INTO activity_log (`utc_timestamp`, type, action, status, auth_platform, auth_ipv4,
                                              auth_email, auth_org, auth_id, auth_role, target_id,
                                              target_role, message)
                    VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) """
        params = (
            utc_timestamp,
            log_type,
            action,
            status,
            auth_platform,
            auth_ipv4,
            auth_email,
            auth_org,
            auth_id,
            auth_role,
            target_id,
            target_role,
            message,
        )
        with cnx.cursor() as cursor:
            cursor.execute(query, params)
            cnx.commit()
    except GeneralException as e:
        logging.exception(e)
