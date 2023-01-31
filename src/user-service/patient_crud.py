import hashlib
import json
import logging
import uuid
from datetime import datetime
from http import HTTPStatus

import boto3
import pymysql
from admin_crud import get_customer_admin_by_id, get_org_customer_admins
from custom_exception import GeneralException
from email_template import CDSUpdateEmail, UpdatePatientEmail, send_mail_to_user
from exceptions import DataValidation, InvalidNewUserError
from log_changes import get_patient_log_state, log_change
from shared import (
    find_user_by_external_id,
    find_user_by_internal_id,
    get_db_connect,
    get_headers,
    get_phi_data,
    get_phi_data_list,
    get_user_by_id,
    get_user_org_ids,
    read_as_dict,
    strip_dashes,
)
from sqls.patient import (
    ACTIVATE_DEACTIVATE_PATIENT,
    DELETE_PATIENT_NETWORK,
    DELETE_PATIENT_ORG,
    INSERT_EXCEPTION,
    INSERT_PATIENT,
    INSERT_PATIENT_ORG,
    PATIENT_CAREGIVER_NETWORK,
    PATIENT_DETAILS_BY_REF_UID,
    PATIENT_DETAILS_QUERY,
    PATIENT_DEVICE_QUERY,
    PATIENT_LISTING_QUERY,
    PATIENT_PROVIDER_NETWORK,
    PATIENT_UPDATE_QUERY,
    SSN_DOB_FNAME_LNAME_QUERY,
)
from sqls.patient_device import (
    GET_DEVICE_DETAILS,
    GET_DEVICE_FROM_DEVICE_READING,
    GET_DEVICE_PAIRING_STATUS,
    GET_PATIENT_DETAILS,
    INSERT_DEVICE_PAIRING,
    UPDATE_DEVICE_PAIRING_STATUS,
)
from sqls.user import INSERT_DELETED_USER
from user_utils import (
    _execute_network_fixes,
    add_to_user_exception,
    create_update_user_profile,
    create_user_in_cognito,
    format_user_fields,
    get_next_sequence,
    get_org_name,
    get_user_via_email,
    remove_user,
    update_email_in_cognito,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()


def notify_customer_admins(cnx, customer_admin_id, form_data):
    """Send notification to other customer Admins"""
    customer_admin = get_customer_admin_by_id(cnx, customer_admin_id)
    result = get_org_customer_admins(cnx, customer_admin["org_id"])[1]
    external_id_list = [admin["external_id"] for admin in result]
    admins_list_by_org = get_phi_data_list(external_id_list, dynamodb)
    email_to_list = [item["email"] for item in admins_list_by_org.values()]
    # TODO these hardcoded values need to be removed.
    org_details = get_org_name(cnx, customer_admin["org_id"])
    update_email = UpdatePatientEmail(form_data["first_name"], org_details["name"])
    for email in email_to_list:
        if email != customer_admin["email"]:
            send_mail_to_user([email], update_email)


def get_patient_network_users_on_org(cnx, patient_id: int, org_id: int) -> list:
    """
    Networks associated with patient
    :params org_id, patient_id
    :Return list of all patient
    """
    network_list = []
    network_providers = read_as_dict(
        cnx, PATIENT_PROVIDER_NETWORK, {"patient_id": patient_id, "org_id": org_id}
    )
    network_caregivers = read_as_dict(
        cnx, PATIENT_CAREGIVER_NETWORK, {"patient_id": patient_id, "org_id": org_id}
    )
    if network_providers:
        network_list.extend(network_providers)
    if network_caregivers:
        network_list.extend(network_caregivers)
    return network_list


def get_all_patients(cnx, auth_user: dict) -> tuple:
    """
    Get all the Patients Associated to this Organization
    :params org_id
    :Return list of all patient
    """
    org_id = auth_user["userOrg"]
    patient_data = read_as_dict(cnx, PATIENT_LISTING_QUERY, {"org_id": org_id})
    patient_external_ids = [patient["external_id"] for patient in patient_data]
    phi_data = get_phi_data_list(patient_external_ids, dynamodb)
    for patient in patient_data:
        try:
            patient_info = phi_data.get(patient["external_id"], {})
            if patient_info:
                name = (
                    patient_info.get("first_name") + " " + patient_info.get("last_name")
                )
                patient.update(
                    {
                        "name": name,
                        "first_name": patient_info.get("first_name"),
                        "last_name": patient_info.get("last_name"),
                        "role": patient_info.get("role"),
                    }
                )
        except GeneralException as err:
            logger.error(err)
    logger.info("Successfully fetched patient details for org_id %s", org_id)
    return 200, patient_data


def get_patient(cnx, patient_id: int, auth_user: dict) -> tuple:
    """
    Get patient Details
    :params patient_id, auth_user
    """
    org_id = auth_user["userOrg"]
    patient_details = read_as_dict(
        cnx, PATIENT_DETAILS_QUERY, {"patient_id": patient_id}, True
    )
    if patient_details:
        phi_data = get_phi_data(patient_details["external_id"], dynamodb)
        patient_details.update(phi_data)
        params = {"patient_id": patient_details["internal_id"]}
        device_details = read_as_dict(cnx, PATIENT_DEVICE_QUERY, params, True)
        patient_details.update(
            {
                "name": f"{phi_data.get('first_name','') if phi_data else ''} {phi_data.get('last_name','') if phi_data else ''}".strip(),
                "first_name": phi_data.get("first_name", "") if phi_data else "",
                "last_name": phi_data.get("last_name", "") if phi_data else "",
                "cell_country_code": phi_data.get("cell_country_code", "+1")
                if phi_data
                else "+1",
                "home_tel_country_code": phi_data.get("home_tel_country_code", "+1")
                if phi_data
                else "+1",
                "cell": strip_dashes(str(phi_data.get("cell", ""))) if phi_data else "",
                "home_tel": strip_dashes(str(phi_data.get("home_tel", "")))
                if phi_data
                else "",
                "middle_name": phi_data.get("middle_name", "") if phi_data else "",
            }
        )
        if device_details:
            patient_details.update(device_details)
        else:
            patient_details.update({"device_pairing": "", "start_date": ""})
        patient_details["patient_network"] = get_patient_network_users_on_org(
            cnx, patient_id, org_id
        )
        return HTTPStatus.OK, patient_details
    return HTTPStatus.NOT_FOUND, "Requested Patient Doesn't Exist"


def update_patient(
    cnx, patient_id: int, form_data: dict, via_cds=None, auth_user=None
) -> tuple:
    """
    Update the patient buy patient_id
    :params patient_id, form_data
    """
    try:
        restricted_fields = ["username"] if via_cds else ["ssn", "username"]
        patient = read_as_dict(
            cnx, PATIENT_DETAILS_QUERY, {"patient_id": patient_id}, fetchone=True
        )
        if not patient:
            return HTTPStatus.NOT_FOUND, "Patient Doesn't exist"
        old_state = get_patient_log_state(cnx, patient_id)
        prev_phi = get_phi_data(patient["external_id"], dynamodb)
        form_data["external_id"] = patient["external_id"]
        phi_data = prev_phi.copy()
        if prev_phi["email"] != form_data["email"] and get_user_via_email(
            form_data["email"],
            "patient",
        ):
            raise InvalidNewUserError(
                101, "User with this email Already exists on system"
            )
        profile_data = format_user_fields(form_data, "patients")
        for attr in restricted_fields:
            if attr in profile_data:
                profile_data.pop(attr)
        for attr in profile_data:
            phi_data.update({attr: form_data.get(attr) or ""})
        upd_phi = create_update_user_profile(phi_data)
        if prev_phi["email"] != upd_phi["email"]:
            if update_email_in_cognito(
                prev_phi["username"], upd_phi["email"], "WebApp"
            ):
                logger.info("Email Successfully updated In cognito")
        if "remote_monitoring" not in form_data:
            form_data["remote_monitoring"] = "N"
        try:
            params = {
                "remote_monitoring": form_data["remote_monitoring"],
                "update_date": datetime.utcnow(),
                "hash_dob": get_hash_value(upd_phi["dob"]),
                "hash_fn": get_hash_value(upd_phi["first_name"].lower()),
                "hash_ssn": get_hash_value(upd_phi["ssn"]),
                "hash_ln": get_hash_value(upd_phi["last_name"].lower()),
                "patient_id": patient["id"],
            }
            with cnx.cursor() as cursor:
                cursor.execute(PATIENT_UPDATE_QUERY, params)
                cnx.commit()
        except pymysql.MySQLError as err:
            logger.error(err)
            return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"
        new_state = get_patient_log_state(cnx, patient_id)
        patient["role"] = "patient"
        log_change(cnx, old_state, new_state, auth_user, patient)
        return HTTPStatus.OK, {
            "id": patient["id"],
            "username": upd_phi["username"],
            "name": upd_phi["first_name"] + " " + upd_phi["last_name"],
            "first_name": upd_phi["first_name"],
            "last_name": upd_phi["last_name"],
            "role": "patient",
            "internal_id": patient["internal_id"],
            "remote_monitoring": patient["remote_monitoring"],
        }
    except InvalidNewUserError as err:
        return err.code, err.msg
    except GeneralException as err:
        logger.exception(err)
        if create_update_user_profile(prev_phi):
            logger.info("Previous Info Restored")
        return HTTPStatus.INTERNAL_SERVER_ERROR, "Error while Updating patient"


def delete_patient(cnx, patient_id: int, auth_user: dict) -> tuple:
    """Delete a patient"""
    org_id = auth_user["userOrg"]
    patient = read_as_dict(
        cnx, PATIENT_DETAILS_QUERY, {"patient_id": patient_id}, fetchone=True
    )
    if not patient:
        return HTTPStatus.NOT_FOUND, "Patient Not Found"
    try:
        with cnx.cursor() as cursor:
            params = {
                "role": "patient",
                "org_id": org_id,
                "user_id": patient["internal_id"],
            }
            cursor.execute(INSERT_DELETED_USER, params)
            cursor.execute(DELETE_PATIENT_ORG, {"id": patient["id"], "org_id": org_id})
            cnx.commit()
        orgs = get_user_org_ids(cnx, "patient", user_id=patient["id"])
        if not bool(orgs):
            with cnx.cursor() as cursor:
                cursor.execute(DELETE_PATIENT_NETWORK, {"patient_id": patient["id"]})
                cursor.execute(
                    ACTIVATE_DEACTIVATE_PATIENT, {"value": 0, "id": patient["id"]}
                )
                cnx.commit()
        else:
            _execute_network_fixes(cnx, None, patient["id"])
        return HTTPStatus.OK, "Success"
    except pymysql.MySQLError as err:
        logger.error(err)
        cnx.rollback()
        return HTTPStatus.INTERNAL_SERVER_ERROR, err


def create_patient(cnx, form_data: dict, org_id: int) -> tuple:
    """Create New Patient"""
    try:
        cognito_user = {}
        phi_data = {}
        name = form_data["first_name"] + " " + form_data["last_name"]
        org_name = get_org_name(cnx, org_id).get("name", "")
        code, cognito_user = create_user_in_cognito(
            form_data["username"], form_data["email"], name, org_name
        )
        if code != 200:
            raise InvalidNewUserError(code, cognito_user)
        user_sub = cognito_user.get("sub")
        profile_info = format_user_fields(form_data, "patients")
        profile_info["external_id"] = user_sub
        phi_data = create_update_user_profile(profile_info)
        if "remote_monitoring" not in form_data:
            form_data["remote_monitoring"] = "N"
        params = {
            "external_id": phi_data["external_id"],
            "internal_id": get_next_sequence(cnx),
            "ref_uid": form_data.get("ref_uid", None),
            "hash_ssn": get_hash_value(form_data["ssn"]),
            "hash_dob": get_hash_value(form_data["dob"]),
            "hash_fname": get_hash_value(form_data["first_name"].lower()),
            "hash_lname": get_hash_value(form_data["last_name"].lower()),
            "remote_monitoring": form_data["remote_monitoring"],
            "activated": 1,
        }
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_PATIENT, params)
            patient_id = cursor.lastrowid
            cursor.execute(INSERT_PATIENT_ORG, {"org_id": org_id, "id": patient_id})
            cnx.commit()
        response = {
            "id": patient_id,
            "first_name": phi_data["first_name"],
            "last_name": phi_data["last_name"],
            "name": phi_data["first_name"] + " " + phi_data["last_name"],
            "role": "patient",
            "username": phi_data["username"],
        }
        logger.info("Patient Created Successfully with id %s", patient_id)
        return HTTPStatus.OK, response
    except InvalidNewUserError as err:
        return err.code, err.msg
    except GeneralException as err:
        logger.error(err)
        if cognito_user or phi_data:
            remove_user(cognito_user, phi_data)
        return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"


def get_patient_by_cds_id(cnx, ref_uid: str) -> dict:
    """Get the patient by ref_uid"""
    return read_as_dict(
        cnx, PATIENT_DETAILS_BY_REF_UID, {"ref_uid": ref_uid}, fetchone=True
    )


def get_hash_value(attr: str) -> str:
    """Create a hash value in sha256 and returns it"""
    hash256 = hashlib.sha256(attr.encode())
    return hash256.hexdigest()


def attributes_exists(cnx, hash_dict: dict) -> dict:
    """Query the patient table for find any match for ssn, fname, lname, dob"""
    params = {
        "ssn": hash_dict["ssn"],
        "dob": hash_dict["dob"],
        "fname": hash_dict["first_name"],
        "lname": hash_dict["last_name"],
    }
    return read_as_dict(cnx, SSN_DOB_FNAME_LNAME_QUERY, params)


def list_matching_fields(cnx, pat_info):
    """Find the matching fields and the record id"""
    attributes = ["ssn", "dob", "first_name", "last_name"]
    hash_attr_dict = {}
    for key in attributes:
        if key in ("first_name", "last_name"):
            hash_attr_dict[key] = get_hash_value(pat_info[key].lower())
        else:
            hash_attr_dict[key] = get_hash_value(pat_info[key])
    matched_results = attributes_exists(cnx, hash_attr_dict)
    matched_dict = {}
    for row in matched_results:
        match = dict(row.items() & hash_attr_dict.items())
        matched_dict[row["external_id"]] = list(match.keys())
    return matched_dict


def create_exception(cnx, matching_dict, form_data, customer_admin):
    """Create and exception in exception table"""
    customer_admin_id = customer_admin["id"]
    auth_org_id = customer_admin["org_id"]
    for ext_id, fields in matching_dict.items():
        if len(fields) < 2:
            continue
        matching_org_ids = get_user_org_ids(cnx, "patients", external_id=ext_id)
        for org_id in matching_org_ids:
            if org_id == auth_org_id or (org_id != auth_org_id and len(fields) < 3):
                status = "APPROVED"
            else:
                status = "PENDING"
            params = {
                "matching_external_id": ext_id,
                "ref_uid": form_data["ref_uid"],
                "file_path": form_data["file_path"],
                "matching_fields": ",".join(fields),
                "org_id": form_data["org_id"],
                "matching_org_id": org_id,
                "status": status,
                "comments": None,
                "created_by": customer_admin_id,
                "created_on": datetime.utcnow(),
            }
            try:
                with cnx.cursor() as cursor:
                    cursor.execute(INSERT_EXCEPTION, params)
                    cnx.commit()
            except pymysql.MySQLError as err:
                logger.error(err)
                return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"
    return HTTPStatus.OK, "EXCEPTION"


def get_device_imei(cnx, imei):
    """
    Get Complete Device IMEI from the last 6 digits.
    """
    active_device = read_as_dict(
        cnx, GET_DEVICE_FROM_DEVICE_READING.format(imei), fetchone=True
    )
    return HTTPStatus.OK, active_device


def get_patient_details_with_device(cnx, patient_internal_id):
    """
    Get Patient and paired device details for the selected patient
    """
    params = {"id": patient_internal_id}
    patient_details = read_as_dict(cnx, GET_PATIENT_DETAILS, params, fetchone=True)
    device_details = read_as_dict(cnx, GET_DEVICE_DETAILS, params, fetchone=True)
    if isinstance(patient_details, dict):
        if device_details and isinstance(device_details, dict):
            patient_details.update(device_details)
        else:
            patient_details.update({"device_pairing": None, "start_date": None})
        phi_data = get_phi_data(patient_details["external_id"], dynamodb)
        if phi_data:
            patient_details.update(
                {
                    "name": f"{phi_data.get('first_name')} {phi_data.get('last_name')}",
                    "first_name": phi_data.get("first_name") if phi_data else "",
                    "last_name": phi_data.get("last_name") if phi_data else "",
                }
            )
    return patient_details


def pair_device(cnx, imei, patient_internal_id, start_date):
    """
    Pair a Device
    """
    params = {
        "patient_internal_id": patient_internal_id,
        "imei": imei,
        "start_date": start_date,
        "active": "Y",
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_DEVICE_PAIRING, params)
            cnx.commit()
        logger.info(
            "Successfully assigned device ::%s to patient ::%s",
            imei,
            patient_internal_id,
        )
        patient_details = get_patient_details_with_device(cnx, patient_internal_id)
        return HTTPStatus.OK, patient_details
    except pymysql.MySQLError as err:
        logger.error(err)
    return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"


def get_device_pairing_data(cnx, imei):
    """
    Returns device pairing data given the device IMEI
    """
    device_data = read_as_dict(
        cnx, GET_DEVICE_PAIRING_STATUS, {"imei": imei}, fetchone=True
    )
    return dict(device_data or {})


def unpair_device(cnx, device_pairing_id, end_date):
    """
    Unpair A Device
    """
    try:
        with cnx.cursor() as cursor:
            cursor.execute(
                UPDATE_DEVICE_PAIRING_STATUS,
                {"end_date": end_date, "device_pairing_id": device_pairing_id},
            )
            cnx.commit()
        return HTTPStatus.OK, "SUCCESS"
    except pymysql.MySQLError as err:
        logger.error(err)
    return HTTPStatus.INTERNAL_SERVER_ERROR, "ERROR"


def update_insert_device_pairing(cnx, available_device_imei, patient):
    """
    This function pairs device to the selected patient if the device is available
    The function logs an error if the device is either already paired
    to the same or a different patient
    """
    current_patient_id = patient.get("internal_id")
    if available_device_imei and current_patient_id:
        device_data = get_device_pairing_data(cnx, available_device_imei)
        if device_data:
            device_imei_end = available_device_imei[-6:]
            if int(device_data["patient_internal_id"]) == int(current_patient_id):
                logger.error("The Device is already paired to this patient")
                return
            paired_patient_data = find_user_by_internal_id(
                cnx, device_data["patient_internal_id"], "patient"
            )
            log_string = "The device {0} is already paired to another patient ".format(
                device_imei_end
            )
            log_string += "with internal_id = {0} and external_id = {1}".format(
                device_data["patient_internal_id"],
                paired_patient_data.get("external_id", "")
                if paired_patient_data
                else "",
            )
            logger.error(log_string)
            return
        current_date = datetime.utcnow()
        pair_device(cnx, available_device_imei, current_patient_id, current_date)


def link_device_to_patient(cnx, patient_id: int, device_id: str):
    """
    This Function:
    1. Gets complete IMEI for device
    2. Gets patient data for the entered patient id
    3. Tries to pair the entered device to the selected patient
    """
    try:
        status_code, available_device = get_device_imei(cnx, device_id)
        patient_data = get_user_by_id(cnx, patient_id, "patient")
        if not patient_data:
            logger.error("Patient not found for the entered patient id")
            return
        if not available_device or not isinstance(available_device, dict):
            logger.error("No Unpaired Device found for the entered device ID")
            return

        available_device_imei = available_device.get("imei", "")
        if status_code == HTTPStatus.OK and len(available_device_imei) != 15:
            logger.error("Failed to find entered device in device reading")
            return
        patient = patient_data[0]
        update_insert_device_pairing(cnx, available_device_imei, patient)

    except pymysql.MySQLError as err:
        logger.exception(err)
    except GeneralException as err:
        logger.exception(err)


def process_patient_by_cds(cnx, form_data, customer_admin_id):
    """Process the patient records via cds"""
    customer_admin = get_customer_admin_by_id(cnx, customer_admin_id)
    customer_admin.update(get_phi_data(customer_admin["external_id"], dynamodb))
    logger.info("username %s", form_data["username"])
    org_id = customer_admin["org_id"] if customer_admin else None
    existing_patient = get_patient_by_cds_id(cnx, form_data["ref_uid"])
    matched_dict = list_matching_fields(cnx, form_data)
    form_data["org_id"] = org_id
    auth_user = {
        "platform": "CronTask",
        "ipv4": "0.1.0.1",
        "auth_id": customer_admin_id,
        "userRole": "cron",
        "auth_org": org_id,
    }
    try:
        if existing_patient:
            logger.info("CDS ID Exists , Update CDS record")
            external_id = existing_patient["external_id"]
            logger.info(
                "Existing user updated by CronTask. ref_id= %s", form_data["ref_uid"]
            )
            # Todo the below logic may need to be enabled if cds tries to update some other patient info wih new info
            #  documented as part of 1.c identity management in confluence
            # if matched_dict:
            #     matched_dict.pop(external_id)
            # for match_id, fields in matched_dict.items():
            #     if len(fields) > 2 or bool(set(fields) & {"ssn", "dob"}):
            #         logger.info("Matching patient external_id %s", match_id)
            #         status_code, msg = create_exception(
            #             cnx, matched_dict, form_data, customer_admin
            #         )
            #         return status_code, msg
            org_ids = get_user_org_ids(cnx, "patient", external_id=external_id)
            if len(org_ids) > 1:
                logger.info("Updating a patient with notify")
                status_code, msg = update_patient(
                    cnx,
                    existing_patient["id"],
                    form_data,
                    via_cds=True,
                    auth_user=auth_user,
                )
                if (
                    status_code == HTTPStatus.OK
                    and isinstance(msg, dict)
                    and "device" in form_data
                    and "id" in msg
                ):
                    link_device_to_patient(cnx, msg["id"], form_data["device"])
                notify_customer_admins(cnx, customer_admin_id, form_data)
                return status_code, msg
            logger.info("Updating a patient without notify")
            status_code, msg = update_patient(
                cnx,
                existing_patient["id"],
                form_data,
                via_cds=True,
                auth_user=auth_user,
            )
            if (
                status_code == HTTPStatus.OK
                and isinstance(msg, dict)
                and "device" in form_data
                and "id" in msg
            ):
                link_device_to_patient(cnx, msg["id"], form_data["device"])
            content = (
                f"Existing user updated by CronTask. ref_id={form_data['ref_uid']}"
            )
            cds_update_email = CDSUpdateEmail(content, "Updated user")
            send_mail_to_user([customer_admin["email"]], cds_update_email)
            return status_code, msg
        logger.info("New Record from CDS")
        for match_id, fields in matched_dict.items():
            logger.info(f"Matching Id {match_id} Matching fields {fields}")
            if len(fields) >= 2:
                status_code, msg = create_exception(
                    cnx, matched_dict, form_data, customer_admin
                )
                return status_code, msg
        logger.info("Creation of New user via CDS")
        status_code, msg = create_patient(cnx, form_data, org_id)
        if (
            status_code == HTTPStatus.OK
            and isinstance(msg, dict)
            and "device" in form_data
            and "id" in msg
        ):
            link_device_to_patient(cnx, msg["id"], form_data["device"])
        if isinstance(status_code, HTTPStatus):
            return status_code.value, msg
        return status_code, msg
    except GeneralException as e:
        logger.exception(e)
        logger.info(form_data)
        content = f"CronTask failed to process user. Email {form_data['email']} and ref_uid {form_data['ref_uid']}"
        cds_update_email = CDSUpdateEmail(content, "ERROR processing user by CDS")
        send_mail_to_user([customer_admin["email"]], cds_update_email)


def add_new_patient(cnx, form_data, auth_user):
    """
    Add a Patient via Org Portal
    """
    existing_data = []
    try:
        new_record = True
        auth_org_id = auth_user["userOrg"]
        customer_admin = get_customer_admin_by_id(cnx, auth_user["id"])
        matched_dict = list_matching_fields(cnx, form_data)
        for match_id, fields in matched_dict.items():
            if len(fields) >= 2:
                new_record = False
                break
        if new_record:
            status_code, user_result = create_patient(cnx, form_data, auth_org_id)
            return status_code, user_result
        user_result = {}
        exception_id = str(uuid.uuid4())
        form_data["exception_id"] = exception_id
        form_data["org_id"] = str(auth_org_id)
        resp = add_to_user_exception(form_data)
        form_data["file_path"] = resp["exception_id"]
        for user in matched_dict:
            existing_data.append(get_phi_data(user))
        status_code, msg = create_exception(
            cnx, matched_dict, form_data, customer_admin
        )
        if status_code.value == 200:
            logger.info("Identity match with other patient")
            raise InvalidNewUserError(102, "Identity Match with other patients")
        logger.info("Error while creating Identity match with other patient")
        raise GeneralException("Error while creating user exceptions")
    except InvalidNewUserError as err:
        user_result["errorCode"] = err.code
        user_result["existing_data"] = existing_data
        return HTTPStatus.BAD_REQUEST, user_result


def lambda_handler(event, context):
    """
    Org portal Patient Handler
    """
    auth_user = event["requestContext"].get("authorizer")
    identity = event["requestContext"].get("identity")
    auth_user["ipv4"] = identity.get("sourceIp", None)
    path = event["path"].split("/")
    customer_admin = find_user_by_external_id(
        connection, auth_user["userSub"], auth_user["userRole"]
    )
    auth_user.update(customer_admin)
    if event["httpMethod"] == "GET":
        if "patients" in path:
            status_code, result = get_all_patients(connection, auth_user)
        elif "patient" in path:
            patient_id = event["pathParameters"].get("patient_id")
            status_code, result = get_patient(connection, patient_id, auth_user)
    elif event["httpMethod"] == "PUT":
        patient_id = event["pathParameters"].get("patient_id")
        form_data = json.loads(event["body"])
        status_code, result = update_patient(
            connection, patient_id, form_data, None, auth_user
        )
    elif event["httpMethod"] == "DELETE":
        patient_id = event["pathParameters"].get("patient_id")
        status_code, result = delete_patient(connection, patient_id, auth_user)
    elif event["httpMethod"] == "POST":
        form_data = json.loads(event["body"])
        auth_user["userOrg"] = int(auth_user["userOrg"])
        user_data = {
            "username": form_data.get("username"),
            "first_name": form_data.get("first_name"),
            "last_name": form_data.get("last_name"),
            "middle_name": form_data.get("middle_name"),
            "cell_country_code": form_data.get("cell_country_code", "+1"),
            "home_tel_country_code": form_data.get("home_tel_country_code", "+1"),
            "cell": form_data.get("cell"),
            "email": form_data.get("email"),
            "address_city": form_data.get("address_city"),
            "state": form_data.get("state"),
            "address_zip": form_data.get("address_zip"),
            "dob": form_data.get("dob"),
            "drive_license_number": form_data.get("drive_license_number"),
            "msg": form_data.get("msg_code"),
            "external_id": form_data.get("external_id"),
            "gender": form_data.get("gender"),
            "home_tel": form_data.get("home_tel"),
            "home_addr_1": form_data.get("home_addr_1"),
            "home_addr_2": form_data.get("home_addr_2"),
            "ref_uid": form_data.get("ref_uid"),
            "ssn": form_data.get("ssn"),
            "role": "patient",
        }
        DataValidation(user_data).validate_required_field(
            [
                "first_name",
                "last_name",
                "gender",
                "dob",
                "home_tel",
                "cell",
                "email",
                "home_addr_1",
                "address_city",
                "address_zip",
                "role",
                "ssn",
            ]
        )
        status_code, result = add_new_patient(connection, user_data, auth_user)
    if isinstance(status_code, HTTPStatus):
        status_code = status_code.value
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
