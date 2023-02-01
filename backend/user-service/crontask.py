import json
import logging
import os
import re
from http import HTTPStatus

import paramiko
from custom_exception import GeneralException
from hl7apy.parser import parse_message
from patient_crud import process_patient_by_cds
from shared import get_db_connect, get_secret_manager
from user_utils import state_conversion, str_dob_to_full_date
from username import get_user_name

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()

customer_admin_id = os.getenv("CUSTOMER_ADMIN_ID", "31")
sftp_secret_id = os.getenv("SFTP_SECRET_ID")


def get_sftp_client():
    """
    Returns Open SFTP connection
    """
    try:
        cds_server = get_secret_manager(sftp_secret_id)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=cds_server["host"],
            username=cds_server["username"],
            password=cds_server["password"],
        )
        return client.open_sftp(), cds_server["dir"]
    except GeneralException as err:
        logger.error(err)
        return None, ""


def process_hl7_fields(lines):
    """
    HT7 parser
    """
    full_content = ""
    for line in lines:
        full_content = full_content + line.decode("utf-8") + "\r"
    try:
        m = parse_message(full_content)
    except GeneralException as err:
        logger.error("File not in HL7 format %s", err)
        return HTTPStatus.BAD_REQUEST, "NOT_HL7"

    if "ADT" != m.msh.msh_9.msh_9_1.value:
        return HTTPStatus.BAD_REQUEST, "NOT_ADT"
    if m.msh.msh_9.msh_9_2.value not in ["A01", "A08"]:
        return HTTPStatus.BAD_REQUEST, m.msh.msh_9.msh_9_2.value
    if m.pid.pid_2.value != m.pid.pid_3.value:
        logger.info("patient id2: %s", m.pid.pid_2.value)
        logger.info("patient id3: %s", m.pid.pid_3.value)

    pid17 = m.pid.pid_17.value
    logger.info("religion: [%s]", pid17)
    if pid17 not in ["S", "R"]:
        return HTTPStatus.BAD_REQUEST, "PID17=" + pid17

    device = m.obx.obx_3.value.strip().lower()
    logger.info("device id: [%s]", device)

    email = m.pid.pid_4.value.strip().lower()
    logger.info("email: [%s]", email)
    if len(email) == 0:
        return HTTPStatus.BAD_REQUEST, "NO_EMAIL"
    regex = r"^[a-z0-9+]+[\._]?[a-z0-9]+@\w+[.]\w+$"
    if not re.match(regex, email):
        return HTTPStatus.BAD_REQUEST, "INVALID_EMAIL"
    cell = m.pid.pid_13.pid_13_1.value.strip().replace("-", "")
    if len(cell) == 0:
        return HTTPStatus.BAD_REQUEST, "NO_CELL_NUMBER"
    cell_regex = r"^\d{10}$"
    if not re.match(cell_regex, cell):
        return HTTPStatus.BAD_REQUEST, "INVALID_CELL_NUMBER"
    home_tel = m.pid.pid_13.pid_13_1.value.strip().replace("-", "")
    if home_tel and not re.match(cell_regex, home_tel):
        return HTTPStatus.BAD_REQUEST, "INVALID_HOME_TEL_NUMBER"
    gender = m.pid.pid_8.pid_8_1.value.strip()[0].upper()
    user_data = {
        "first_name": m.pid.pid_5.pid_5_2.value.strip().title(),
        "middle_name": m.pid.pid_5.pid_5_3.value.strip().title(),
        "last_name": m.pid.pid_5.pid_5_1.value.strip().title(),
        "gender": "male" if gender == "M" else "female",
        "email": m.pid.pid_4.value.strip().lower(),
        "role": "patient",
        "address_city": m.pid.pid_11.pid_11_3.value.strip().title(),
        "state": state_conversion(m.pid.pid_11.pid_11_4.value.strip()),
        "address_zip": m.pid.pid_11.pid_11_5.value.strip(),
        "dob": str_dob_to_full_date(m.pid.pid_7.value.strip())[0:10],
        "cell": m.pid.pid_13.pid_13_1.value.strip().replace("-", ""),
        "home_tel": m.pid.pid_13.pid_13_1.value.strip().replace("-", ""),
        "home_addr_1": m.pid.pid_11.pid_11_1.value.strip().title(),
        "ref_uid": m.pid.pid_2.value.strip(),
        "ssn": m.pid.pid_19.value.strip()[-4:],
        "device": device,
    }
    logger.info("user_data ref_uid = %s", user_data["ref_uid"])
    user_data["remote_monitoring"] = "Y" if pid17 == "R" else "N"
    return HTTPStatus.OK, user_data


def update_user_cds(cnx):
    """
    Update user data in CDS
    """
    logger.info("Update User CDS Called")
    sftp_client, directory = get_sftp_client()
    sftp_client.chdir(directory)
    file_list = sftp_client.listdir()
    status_code = HTTPStatus.BAD_REQUEST
    for filename in file_list:
        if filename in ["DONE", "ERROR", "EXCEPTION", "HOLD"] or filename.endswith(
            ".csv"
        ):
            continue
        logger.info(filename)
        remote_file = sftp_client.open(filename, bufsize=32768)
        try:
            lines = remote_file.read().splitlines()
            status_code, user_data = process_hl7_fields(lines)
            if status_code.value != 200:
                logger.error("Error while processing Patient. Reason: %s", user_data)
                return status_code, user_data
            user_data["username"] = get_user_name(
                user_data["first_name"], user_data["last_name"]
            )
            user_data["file_path"] = filename
            status_code, msg_type = process_patient_by_cds(
                cnx, user_data, customer_admin_id
            )
            if msg_type == "EXCEPTION":
                sftp_client.posix_rename(filename, "EXCEPTION/" + filename)
            elif msg_type == "ERROR":
                sftp_client.posix_rename(filename, "ERROR/" + filename)
            else:
                sftp_client.posix_rename(filename, "DONE/" + filename)
        except GeneralException as err:
            logger.error(err)
    return status_code, "CDS processed"


def lambda_handler(event, context):
    """
    Cron task update user cds
    """
    status_code, response = update_user_cds(connection)
    if isinstance(status_code, HTTPStatus):
        status_code = status_code.value
    return {"statusCode": status_code, "body": json.dumps(response)}
