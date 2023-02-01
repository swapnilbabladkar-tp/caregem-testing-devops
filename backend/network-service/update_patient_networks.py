import json
import logging
import os
from datetime import datetime

import boto3
import pymysql
from custom_exception import GeneralException
from log_changes import get_patient_log_state, log_change
from notification import insert_to_care_team_notification_table
from shared import (
    User,
    encrypt,
    find_user_by_external_id,
    get_db_connect,
    get_headers,
    get_phi_data_from_internal_id,
    get_phi_data_list,
    get_s3_config,
    get_user_by_id,
    get_user_org_ids,
)
from sms_util import (
    get_patient_added_to_network_message_content,
    get_phone_number_from_phi_data,
    publish_text_message,
)
from sqls.network import DELETE_USER_NETWORKS, INSERT_USER_TO_PATIENT_NETWORK

aws_region = os.getenv("AWSREGION")
bucket_name = os.getenv("BUCKET_NAME")
file_name = os.getenv("S3_FILE_NAME")
environment = os.getenv("ENVIRONMENT")

s3_client = boto3.client("s3", region_name=aws_region)
dynamodb = boto3.resource("dynamodb")


connection = get_db_connect()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_common_org_id(cnx, patient_id, provider_id):
    """
    Get the common org id.
    :params patient_id, provider_id, cnx obj
    :Return common org_ids
    """
    pat_orgs = get_user_org_ids(cnx, "patient", user_id=patient_id)
    prv_orgs = get_user_org_ids(cnx, "providers", user_id=provider_id)
    common_org = set(pat_orgs).intersection(set(prv_orgs))
    if common_org:
        return list(common_org)
    return None


def get_networks_id_to_deleted(cnx, patient_id, org_id):
    """
    Returns list of all network users connected to the selected patient
    for the input org_id
    """
    query = """ SELECT networks.id AS networks_id
                FROM   networks
                       JOIN providers
                         ON networks.connected_user = providers.username
                       JOIN provider_org
                         ON providers.id = provider_org.providers_id
                WHERE  networks._patient_id = %s
                       AND provider_org.organizations_id = %s
                UNION
                SELECT networks.id AS networks_id
                FROM   networks
                       JOIN caregivers
                         ON networks.connected_user = caregivers.username
                       JOIN caregiver_org
                         ON caregivers.id = caregiver_org.caregivers_id
                WHERE  networks._patient_id = %s
                       AND caregiver_org.organizations_id = %s
            """
    with cnx.cursor() as cursor:
        cursor.execute(query, (patient_id, org_id, patient_id, org_id))
        return [row[0] for row in cursor.fetchall()]


def get_user_of_same_org_not_in_list(cnx, prv_ids, cgiver_ids, patient_id, org_id):
    """
    Returns list of all network users not present in new network list
    """
    p_str = ",".join(["%s"] * len(prv_ids))
    c_str = ",".join(["%s"] * len(cgiver_ids))
    prv_query = """ SELECT networks.id AS networks_id
                FROM   networks
                       JOIN providers
                         ON networks.user_internal_id = providers.internal_id
                       JOIN provider_org
                         ON providers.id = provider_org.providers_id
                WHERE  networks._patient_id = %s
                       AND provider_org.organizations_id = %s
                       AND providers.internal_id NOT IN ({p_str}) """.format(
        p_str=p_str
    )

    care_query = """ SELECT networks.id AS networks_id
                    FROM   networks
                       JOIN caregivers
                         ON networks.user_internal_id = caregivers.internal_id
                       JOIN caregiver_org
                         ON caregivers.id = caregiver_org.caregivers_id
                    WHERE  networks._patient_id = %s
                       AND caregiver_org.organizations_id = %s
                       AND caregivers.internal_id NOT IN ({c_str})""".format(
        c_str=c_str
    )

    with cnx.cursor() as cursor:
        if prv_ids and cgiver_ids:
            query = prv_query + " UNION " + care_query
            cursor.execute(
                query,
                (
                    (
                        patient_id,
                        org_id,
                    )
                    + tuple(prv_ids)
                    + (
                        patient_id,
                        org_id,
                    )
                    + tuple(cgiver_ids)
                ),
            )
        elif prv_ids and not cgiver_ids:
            cursor.execute(
                prv_query,
                (
                    (
                        patient_id,
                        org_id,
                    )
                    + tuple(prv_ids)
                ),
            )
        elif cgiver_ids and not prv_ids:
            cursor.execute(
                care_query,
                (
                    (
                        patient_id,
                        org_id,
                    )
                    + tuple(cgiver_ids)
                ),
            )
        return [row[0] for row in cursor.fetchall()]


def check_user_belong_to_same_org(cnx, org_id, ids, user_type):
    """
    This function checks if the input user ids belong to the same organization
    Returns True of empty list or above condition is fulfilled
    Returns False otherwise
    """
    if not ids:
        return True
    f_str = ",".join(["%s"] * len(ids))
    if user_type == "providers":
        org_table = "provider_org"
        org_column = "providers_id"
    else:
        org_table = "caregiver_org"
        org_column = "caregivers_id"
    query = """ SELECT
                    Count(*)
                FROM   {user_type}
                JOIN {org_table}
                    ON {user_type}.id = {org_table}.{org_column}
                WHERE  {org_table}.organizations_id = %s
                    AND {user_type}.internal_id IN ({f_str})
            """.format(
        user_type=user_type, org_table=org_table, org_column=org_column, f_str=f_str
    )

    with cnx.cursor() as cursor:
        cursor.execute(query, (org_id,) + tuple(ids))
        result = cursor.fetchone()
    if result[0] != len(ids):
        return False
    return True


def get_name_from_phi_data(phi_data):
    """
    Returns name string with PHI data as input
    """
    return f"{phi_data['first_name']}, {phi_data['last_name']}"


def get_notification_details(
    added_member_id,
    phi_data_dict,
    added_member_internal_id_map,
    patient_data,
):
    """
    Returns Notification Detail based on input data
    """
    patient_phi_data = phi_data_dict[patient_data["external_id"]]
    patient_name = get_name_from_phi_data(patient_phi_data)
    added_member_external_id = added_member_internal_id_map[added_member_id][
        "external_id"
    ]
    added_member_degree = added_member_internal_id_map[added_member_id].get("degree")
    added_member_specialty = added_member_internal_id_map[added_member_id].get(
        "specialty"
    )
    added_member_phi_data = phi_data_dict[added_member_external_id]
    added_member_name = get_name_from_phi_data(added_member_phi_data)
    if added_member_degree and added_member_specialty:
        return f"{added_member_name},{added_member_degree} {added_member_specialty} has been added to {patient_name}'s care team"
    return f"{added_member_name} has been added to {patient_name}'s care team"


def insert_notification_for_network_providers(
    patient_data,
    users,
    added_member_internal_ids,
    auth_user,
    added_member_internal_id_map,
):
    """
    This Function:
    1. Extracts external_ids from network user list
    2. Get PHI data for all network users and patient
    3. Insert Notification regarding Careteam addition to all network users
    """
    # extract external_ids from network user list
    external_ids = [user["external_id"] for user in users]
    # append patient_external id to list
    external_ids.append(patient_data["external_id"])
    # get phi_data for all users as a dict with external_id's of users as the key
    phi_data_dict = get_phi_data_list(external_ids, dynamodb)
    current_time = datetime.utcnow()
    DEFAULT_NOTIFICATION_STATUS = 1
    DEFAULT_NOTIFICATION_LEVEL = 1
    for added_member_id in added_member_internal_ids:
        for user in users:
            # generate notification detail string for each network user
            notification_details = get_notification_details(
                added_member_id=added_member_id,
                phi_data_dict=phi_data_dict,
                added_member_internal_id_map=added_member_internal_id_map,
                patient_data=patient_data,
            )
            # insert row into care_team_notifications table for each network member
            insert_to_care_team_notification_table(
                ct_member_internal_id=added_member_id,
                patient_internal_id=patient_data["internal_id"],
                notifier_internal_id=user["internal_id"],
                level=DEFAULT_NOTIFICATION_LEVEL,
                notification_details=encrypt(notification_details),
                created_on=current_time,
                created_by=auth_user["internal_id"],
                updated_on=current_time,
                updated_by=auth_user["internal_id"],
                notification_status=DEFAULT_NOTIFICATION_STATUS,
            )
    return


def get_existing_network_users(cnx, patient_id, users):
    """
    Returns list of internal_ids for network users of patient
    """
    int_ids = [user["internal_id"] for user in users if user]
    f_str = ",".join(["%s"] * len(int_ids))
    query = """ SELECT user_internal_id
                FROM   networks
                WHERE  _patient_id = %s
                AND    user_internal_id IN ({f_str})
            """.format(
        f_str=f_str
    )
    with cnx.cursor() as cursor:
        cursor.execute(query, (patient_id,) + tuple(int_ids))
        return [row[0] for row in cursor.fetchall()]


def send_sms_to_alert_receivers(
    cnx, alert_receiver, user, patient_added_to_network_message_content
):
    """
    Sends SMS to network providers who have alert receiver turned on for the patient
    """
    # Check if user has set alert_receiver value to 1 and send SMS only if it is 1 (possible values are 0 or 1)
    if alert_receiver:
        # get phi_data of added member from DynamodDB
        phi_data = get_phi_data_from_internal_id(
            cnx, dynamodb, user["internal_id"], user["role"]
        )
        phone_number = get_phone_number_from_phi_data(phi_data)
        # send SMS to the cell number of added member
        try:
            message_id = publish_text_message(
                phone_number, patient_added_to_network_message_content
            )
            logger.info(f"Message sent with message ID : {message_id}")
        except GeneralException:
            logger.exception("Failed to send Message")


def get_alert_receiver(user):
    """
    Returns Alert receiver value for the user
    """
    if user["role"] == "caregiver":
        alert_receiver = 0
    else:
        alert_receiver = user["alert_receiver"]
    return alert_receiver


def delete_all_patient_networks(cnx, patient_id, org_id):
    """
    Delete all networks for the input patient in given org
    """
    network_ids = get_networks_id_to_deleted(cnx, patient_id, org_id)
    f_str = ",".join(["%s"] * len(network_ids))
    query = DELETE_USER_NETWORKS.format(f_str=f_str)
    try:
        with cnx.cursor() as cursor:
            cursor.execute(query, tuple(network_ids))
            cnx.commit()
    except pymysql.MySQLError as err:
        logger.error(err)


def update_patient_network(cnx, patient_id, users, auth_user):
    """
    Update Patient network data with input user list
    Insert Update notification for added users
    Send SMS to added users regarding addition to care team
    """
    org_id = auth_user["userOrg"]
    old_patient_state = get_patient_log_state(cnx, patient_id)
    if len(users) == 0:
        delete_all_patient_networks(cnx=cnx, patient_id=patient_id, org_id=org_id)
    else:
        selected_provider_ids = [
            int(user["internal_id"])
            for user in users
            if user["role"] in User.PROVIDER_ROLES.value
        ]
        selected_caregivers_ids = [
            int(user["internal_id"])
            for user in users
            if user and user["role"] == "caregiver"
        ]
        if not check_user_belong_to_same_org(
            cnx, org_id, selected_provider_ids, "providers"
        ):
            raise ValueError("Some users doesn't belong to your Organization!")
        if not check_user_belong_to_same_org(
            cnx, org_id, selected_caregivers_ids, "caregivers"
        ):
            raise ValueError("Some users doesn't belong to your Organization!")
        network_ids = get_user_of_same_org_not_in_list(
            cnx, selected_provider_ids, selected_caregivers_ids, patient_id, org_id
        )
        try:
            with cnx.cursor() as cursor:
                if network_ids:
                    f_str = ",".join(["%s"] * len(network_ids))
                    cursor.execute(
                        "DELETE FROM networks WHERE id IN({f_str})".format(f_str=f_str),
                        tuple(network_ids),
                    )

                existing_users = get_existing_network_users(cnx, patient_id, users)
                s3_config = get_s3_config(bucket_name, file_name, s3_client)
                patient_added_to_network_message_content = (
                    get_patient_added_to_network_message_content(
                        s3_config.get(environment, {}).get("WebApp", "")
                    )
                )
                added_member_internal_ids = []
                added_member_internal_id_map = {}
                patient_data_list = get_user_by_id(cnx, patient_id, "patient")
                patient_data = patient_data_list[0] if patient_data_list else {}
                for user in users:
                    if user["internal_id"] in existing_users:
                        continue
                    # The alert_receiver value represents if user wishes to receive SMS communication (Caregivers will never have SMS sent to them)
                    alert_receiver = get_alert_receiver(user)
                    record = (
                        user["username"],
                        user["role"],
                        patient_id,
                        alert_receiver,
                        user["internal_id"],
                    )
                    added_member_internal_ids.append(user["internal_id"])
                    added_member_internal_id_map.update({user["internal_id"]: user})
                    cursor.execute(INSERT_USER_TO_PATIENT_NETWORK, record)
                    send_sms_to_alert_receivers(
                        cnx=cnx,
                        alert_receiver=alert_receiver,
                        patient_added_to_network_message_content=patient_added_to_network_message_content,
                        user=user,
                    )
                # Add Notification regarding added members to each network member
                insert_notification_for_network_providers(
                    patient_data,
                    users,
                    added_member_internal_ids,
                    auth_user,
                    added_member_internal_id_map,
                )
                cnx.commit()
        except pymysql.MySQLError as err:
            logger.error(err)
        except GeneralException as e:
            logger.info(e)
    new_patient_state = get_patient_log_state(cnx, patient_id)
    target_user_list = get_user_by_id(cnx, patient_id, "patient")
    target_user: dict = target_user_list[0] if target_user_list else {}
    target_user["role"] = "patient"
    log_change(cnx, old_patient_state, new_patient_state, auth_user, target_user)
    return {"message": "success"}


def lambda_handler(event, context):
    """
    Handler Function
    """
    auth_user = event["requestContext"].get("authorizer")
    patient_id = event["pathParameters"].get("patient_id")
    identity = event["requestContext"].get("identity")
    auth_user["ipv4"] = identity.get("sourceIp", None)
    form_data = json.loads(event["body"])
    users = form_data["users"]
    user = find_user_by_external_id(
        connection, auth_user["userSub"], auth_user["userRole"]
    )
    auth_user.update(user)
    if auth_user.get("userOrg"):
        response = update_patient_network(connection, patient_id, users, auth_user)
    else:
        org_ids = get_common_org_id(connection, patient_id, user["id"]) if user else []
        print(org_ids)
        if org_ids:
            auth_user["userOrg"] = org_ids[0]
        response = update_patient_network(connection, patient_id, users, auth_user)
    return {"statusCode": 200, "body": json.dumps(response), "headers": get_headers()}
