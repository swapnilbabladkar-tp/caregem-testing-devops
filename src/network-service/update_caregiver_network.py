import json
import logging

from log_changes import get_caregiver_log_state, log_change
from shared import get_db_connect, get_headers, get_user_by_id, read_query

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cnx = get_db_connect()


def get_caregiver_network_base_query():
    """
    Get the Base Select Query for Network And Caregiver
    """
    query = """ SELECT networks.id AS networks_id
                    FROM   networks
                JOIN caregivers on networks.user_internal_id = caregivers.internal_id
                JOIN caregiver_org on caregiver_org.caregivers_id = caregivers.id
                    WHERE networks.user_internal_id = %s
                        AND caregiver_org.organizations_id = %s """
    return query


def get_existing_network_users(cnx, user_internal_id, pat_ids):
    """
    Get the Users which are already in network.
    """
    f_str = ",".join(["%s"] * len(pat_ids))
    query = """ SELECT _patient_id
                FROM networks
                WHERE user_internal_id = %s
                AND _patient_id IN ({f_str})""".format(
        f_str=f_str
    )
    with cnx.cursor() as cursor:
        cursor.execute(query, (user_internal_id,) + tuple(pat_ids))
        return [row[0] for row in cursor.fetchall()]


def get_networks_id_to_deleted(cnx, user_internal_id, pat_ids, org_id):
    """
    Get the networks to be deleted.
    """
    f_str = ",".join(["%s"] * len(pat_ids))
    query = get_caregiver_network_base_query()
    query = query + "AND networks._patient_id NOT IN ({f_str})".format(f_str=f_str)
    with cnx.cursor() as cursor:
        cursor.execute(
            query,
            (
                user_internal_id,
                org_id,
            )
            + tuple(pat_ids),
        )
        return [row[0] for row in cursor.fetchall()]


def update_caregiver_network(caregiver_id, users, auth_user):
    """
    Update the Caregiver Networks.
    """
    org_id = auth_user["userOrg"]
    old_caregiver_state = get_caregiver_log_state(cnx, caregiver_id)
    caregiver_list = get_user_by_id(cnx, caregiver_id, "caregiver")
    caregiver: dict = caregiver_list[0] if caregiver_list else {}
    if len(users) == 0:
        query = get_caregiver_network_base_query()
        network_ids = read_query(cnx, query, (caregiver["internal_id"], org_id))
        network_ids = [ids[0] for ids in network_ids] if network_ids else []
        f_str = ",".join(["%s"] * len(network_ids))
        with cnx.cursor() as cursor:
            cursor.execute(
                "DELETE FROM networks WHERE id IN({f_str})".format(f_str=f_str),
                tuple(network_ids),
            )
            cnx.commit()
    else:
        pat_ids = [user["id"] for user in users]
        network_ids = get_networks_id_to_deleted(
            cnx, caregiver["internal_id"], pat_ids, org_id
        )
        with cnx.cursor() as cursor:
            if network_ids:
                f_str = ",".join(["%s"] * len(network_ids))
                cursor.execute(
                    "DELETE FROM networks WHERE id IN({f_str})".format(f_str=f_str),
                    tuple(network_ids),
                )
            query = """ INSERT INTO networks (connected_user, user_type,
                                              _patient_id, alert_receiver,
                                              user_internal_id)
                    Values (%s, %s, %s, %s, %s)
                    """
            existing_users = get_existing_network_users(
                cnx, caregiver["internal_id"], pat_ids
            )
            for user in users:
                if user["id"] in existing_users:
                    continue
                record = (
                    caregiver["username"],
                    "caregiver",
                    user["id"],
                    0,
                    caregiver["internal_id"],
                )
                cursor.execute(query, record)
            cnx.commit()
    new_caregiver_state = get_caregiver_log_state(cnx, caregiver_id)
    caregiver["role"] = "caregiver"
    log_change(cnx, old_caregiver_state, new_caregiver_state, auth_user, caregiver)

    return {"message": "success"}


def lambda_handler(event, context):
    """
    Handler Function
    """
    auth_user = event["requestContext"].get("authorizer")
    caregiver_id = event["pathParameters"].get("caregiver_id")
    identity = event["requestContext"].get("identity")
    auth_user["ipv4"] = identity.get("sourceIp", None)
    form_data = json.loads(event["body"])
    users = form_data["users"]
    response = update_caregiver_network(caregiver_id, users, auth_user)
    return {"statusCode": 200, "body": json.dumps(response), "headers": get_headers()}
