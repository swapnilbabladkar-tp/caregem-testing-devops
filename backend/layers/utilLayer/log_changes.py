import logging
from datetime import datetime

import boto3
import pymysql
from custom_exception import GeneralException
from shared import (
    get_db_connect,
    get_phi_data,
    get_phi_data_list,
    get_user_org_ids,
    read_as_dict,
)
from utils_query import (
    GET_CAREGIVER_BY_ID,
    GET_CAREGIVER_EXTERNAL_BY_ID,
    GET_CAREGIVERS_DETAILS_BY_INTERNAL_ID,
    GET_CUSTOMER_ADMIN_BY_ID,
    GET_NETWORK_BY_ID,
    GET_ORG_DETAILS,
    GET_PATIENT_BY_ID,
    GET_PATIENT_EXTERNAL_BY_ID,
    GET_PROVIDER_BY_ID,
    GET_PROVIDER_DETAILS_BY_INTERNAL_ID,
    GET_PROVIDER_EXTERNAL_BY_ID,
    INSERT_CHANGE_LOG,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb", "us-east-1")

connection = get_db_connect()


def insert_user_to_pii_hist(user_data):
    """
    Add the User Changes to History Table.
    """
    try:
        table = dynamodb.Table("user_pii_hist")
        external_id = user_data.pop("external_id")
        update_expression = (
            "SET Latest = if_not_exists(Latest, :defaultval) + :incrval,"
        )
        update_expression = update_expression + ",".join(
            f"#{k}=:{k}" for k in user_data
        )
        expression_attribute_values = {":defaultval": 0, ":incrval": 1}
        expression_attribute_values.update({f":{k}": v for k, v in user_data.items()})
        expression_attribute_names = {f"#{k}": k for k in user_data}
        response = table.update_item(
            Key={"external_id": external_id, "version": "v0"},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ReturnValues="UPDATED_NEW",
        )
        latest_version = response["Attributes"]["Latest"]
        user_data.update(
            {"version": "v" + str(latest_version), "external_id": external_id}
        )
        table.put_item(Item=user_data)
        return int(latest_version)
    except GeneralException as e:
        logger.error(e)


def get_connected_user_of_patient(cnx, patient_id):
    """
    Returns list of Providers and Caregivers in the network of the selected patient
    Return Format:
    list of {"id": <user DB id>, "role": <role>, name: <name>, "degree": <degree>}
    """
    user_internal_ids = [
        item["user_internal_id"]
        for item in read_as_dict(cnx, GET_NETWORK_BY_ID, {"patient_id": patient_id})
    ]
    if not user_internal_ids:
        return []
    providers = read_as_dict(
        cnx, GET_PROVIDER_DETAILS_BY_INTERNAL_ID, {"ids": tuple(user_internal_ids)}
    )
    caregivers = read_as_dict(
        cnx, GET_CAREGIVERS_DETAILS_BY_INTERNAL_ID, {"ids": tuple(user_internal_ids)}
    )
    staff = []
    staff_external_ids = []
    if providers:
        staff.extend(providers)
        staff_external_ids.extend(list({item["external_id"] for item in providers}))
    if caregivers:
        staff.extend(caregivers)
        staff_external_ids.extend(list({item["external_id"] for item in caregivers}))
    phi_data = get_phi_data_list(staff_external_ids, dynamodb)
    networks = []
    for user in staff:
        try:
            profile_data = phi_data[user["external_id"]]
            rec = {
                "id": user["id"],
                "role": user["role"],
                "name": "{} {}".format(
                    profile_data["first_name"], profile_data["last_name"]
                ),
                "degree": user["degree"] if "degree" in user else "",
            }
            networks.append(rec)
        except GeneralException as e:
            logger.error(e)
    return networks


def get_org_name(cnx, org_ids):
    """
    Returns list if dict with the org id and name based in input org ids
    Return format:
    list of {"id": <org id>, "name": <org name>}
    """
    return read_as_dict(cnx, GET_ORG_DETAILS, {"ids": tuple(org_ids)})


def patient_log_dict(cnx, patient):
    """
    Returns patient user data in required format for use in change log
    """
    org_ids = get_user_org_ids(cnx, "patient", internal_id=patient["internal_id"])
    return {
        "id": patient["id"],
        "external_id": patient["external_id"],
        "internal_id": patient["internal_id"],
        "role": "patient",
        "organizations": get_org_name(cnx, org_ids),
        "remote_monitoring": patient["remote_monitoring"],
    }


def provider_log_dict(cnx, provider):
    """
    Returns provider user data in required format for use in change log
    """
    org_ids = get_user_org_ids(cnx, "providers", internal_id=provider["internal_id"])
    return {
        "id": provider["id"],
        "external_id": provider["external_id"],
        "internal_id": provider["internal_id"],
        "remote_monitoring": provider["remote_monitoring"],
        "specialty": provider["specialty"],
        "role": provider["role"],
        "group": provider["group"],
        "degree": provider["degree"],
        "alert_receiver": provider["alert_receiver"],
        "organizations": get_org_name(cnx, org_ids),
    }


def caregiver_log_dict(cnx, caregiver):
    """
    Returns caregiver user data in required format for use in change log
    """
    org_ids = get_user_org_ids(cnx, "caregiver", internal_id=caregiver["internal_id"])
    return {
        "id": caregiver["id"],
        "external_id": caregiver["external_id"],
        "internal_id": caregiver["internal_id"],
        "role": "caregiver",
        "organizations": get_org_name(cnx, org_ids),
    }


def get_patient_log_state(cnx, patient_id):
    """
    Returns current state of the patient data for use in change log
    """
    # Combine DB and Dynamo DB information in a single dictionary.
    db_patient = read_as_dict(cnx, GET_PATIENT_BY_ID, {"id": patient_id}, fetchone=True)
    profile_data = get_phi_data(db_patient["external_id"], dynamodb)
    patient_state = {}
    patient_state.update(patient_log_dict(cnx, db_patient))
    patient_state.update(profile_data)
    patient_state["name"] = (
        patient_state.get("first_name") + " " + patient_state["last_name"]
    )
    connected_users = get_connected_user_of_patient(cnx, db_patient["id"])
    patient_state["network"] = connected_users
    return patient_state


def get_provider_log_state(cnx, provider_id):
    """
    Returns current state of the provider data for use in change log
    """
    # Combine DB and Dynamo DB information in a single dictionary.
    db_provider = read_as_dict(
        cnx, GET_PROVIDER_BY_ID, {"id": provider_id}, fetchone=True
    )
    profile_data = get_phi_data(db_provider["external_id"], dynamodb)
    provider_state = {}
    provider_state.update(provider_log_dict(cnx, db_provider))
    provider_state.update(profile_data)
    provider_state["name"] = (
        provider_state.get("first_name") + " " + provider_state["last_name"]
    )
    return provider_state


def get_caregiver_log_state(cnx, caregiver_id):
    """
    Returns current state of the caregiver data for use in change log
    """
    # Combine DB and Dynamo DB information in a single dictionary.
    db_caregiver = read_as_dict(
        cnx, GET_CAREGIVER_BY_ID, {"id": caregiver_id}, fetchone=True
    )
    profile_data = get_phi_data(db_caregiver["external_id"])
    caregiver_state = {}
    caregiver_state.update(caregiver_log_dict(cnx, db_caregiver))
    caregiver_state.update(profile_data)
    caregiver_state["name"] = (
        caregiver_state.get("first_name") + " " + caregiver_state["last_name"]
    )
    return caregiver_state


def get_diff(old_state, new_state):
    """
    This functions returns the difference between
    the old_state and new_state dicts passed as input
    """
    result = list()
    result += [
        f"{key}: removed information field. Last value was {old_state[key]}"
        for key in set(old_state) - set(new_state)
    ]
    result += [
        f"{key}: added new information field. New value is {new_state[key]}"
        for key in set(new_state) - set(old_state)
    ]

    updated_items = [
        key
        for key in set(old_state) & set(new_state)
        if old_state[key] != new_state[key]
    ]
    for key in updated_items:
        if isinstance(old_state[key], list):
            result += [
                f"{key}: removed item {item}"
                for item in old_state[key]
                if item not in new_state[key]
            ]
            result += [
                f"{key}: added item {item}"
                for item in new_state[key]
                if item not in old_state[key]
            ]
        else:
            result += [f"{key}: updated from {old_state[key]} to {new_state[key]}"]

    return result


def get_auth_user_details(cnx, external_id, role):
    """
    Returns user data based on input external_id and role
    in providers / caregivers / patients / customer_admins Tables
    based on role
    """
    auth_user = {}
    if role == "customer_admin":
        query = GET_CUSTOMER_ADMIN_BY_ID
    elif role in ("physician", "case_manager", "nurse"):
        query = GET_PROVIDER_EXTERNAL_BY_ID
    elif role == "patient":
        query = GET_PATIENT_EXTERNAL_BY_ID
    elif role == "caregiver":
        query = GET_CAREGIVER_EXTERNAL_BY_ID
    user = read_as_dict(cnx, query, {"external_id": external_id}, fetchone=True)
    if user:
        auth_user["auth_id"] = user["id"]
        auth_user["auth_role"] = role
        if auth_user["auth_role"] == "customer_admin":
            auth_user["auth_org"] = user["_organization_id"]
        else:
            org_ids = get_user_org_ids(
                cnx, auth_user["auth_role"], external_id=external_id
            )
            auth_user["auth_org"] = org_ids[0]
    return auth_user


def log_change(cnx, old_state, new_state, auth_user=None, target_user=None):
    """
    Inserts row to change_log table based in the old and new state passed as input
    """
    timestamp = datetime.utcnow()
    user_data = {}
    if auth_user:
        if auth_user["userRole"] != "cron":
            user_data = get_auth_user_details(
                cnx, auth_user["userSub"], auth_user["userRole"]
            )
            user_data["auth_id"] = user_data.get("auth_id", None)
        else:
            user_data["auth_id"] = auth_user.get("auth_id", None)
            user_data["auth_role"] = auth_user.get("userRole", None)
            user_data["auth_org"] = auth_user.get("auth_org", None)
        user_data["auth_ipv4"] = auth_user.get("ipv4", None)
        user_data["auth_platform"] = auth_user.get("platform", "WEB")
    if target_user:
        target_id = target_user.get("id", None)
        target_role = target_user.get("role", None)
        external_id = target_user.get("external_id", None)

    change_data = {
        "utc_timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_info": get_diff(old_state, new_state),
        "old_state": old_state,
        "new_state": new_state,
        "external_id": external_id,
    }
    version = insert_user_to_pii_hist(change_data)
    params = {
        "utc_timestamp": timestamp,
        "auth_platform": user_data["auth_platform"],
        "auth_ipv4": user_data["auth_ipv4"],
        "auth_org": user_data["auth_org"],
        "auth_id": user_data["auth_id"],
        "auth_role": user_data["auth_role"],
        "target_id": target_id,
        "target_role": target_role,
        "external_id": external_id,
        "version": version,
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_CHANGE_LOG, params)
        cnx.commit()
    except pymysql.MySQLError as err:
        logger.error(err)
