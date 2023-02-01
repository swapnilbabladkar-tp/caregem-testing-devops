import json
import logging

from shared import get_db_connect, get_headers, get_phi_data_list, read_as_dict

logger = logging.getLogger(__name__)
cnx = get_db_connect()


def get_billing_log(org_id):
    """
    This function returns list of approved bills for the input org id
    """
    query = """ SELECT DATE_FORMAT(billing_detail.date_of_service, '%%a, %%d %%b %%Y %%T') as date_of_service,
                       billing_detail.billing_charge_code,
                       providers.name,
                       patients.username,
                       patients.external_id
                FROM   billing_detail
                       join providers
                         ON providers.internal_id = billing_detail.provider_internal_id
                       join patients
                         ON patients.internal_id = billing_detail.patient_internal_id
                WHERE  billing_detail.billing_org_id = %s
                       AND billing_detail.status = "approve"
            """
    billing_log = read_as_dict(cnx, query, (org_id))
    ext_ids = [d.get("external_id") for d in billing_log] if billing_log else []
    external_ids = list(set(ext_ids))
    phi_data = get_phi_data_list(external_ids)
    bill_charge = []
    prov_name = []
    dates_time = []
    final_set = []
    if billing_log:
        for log in billing_log:
            dates_time.append(log.get("date_of_service", ""))
            prov_name.append(log.get("name", ""))
            billing_charge_code = log.get("billing_charge_code", "").replace("'", '"')
            bill_charge.append(json.loads(billing_charge_code))
    for i, charges_on_a_date in enumerate(bill_charge):
        phi = phi_data[ext_ids[i]]
        for charge in charges_on_a_date:
            item = {
                "date_p": dates_time[i],
                "patient": phi.get("first_name") + " " + phi.get("last_name"),
                "prov": prov_name[i],
                "code": charge.get("code", ""),
                "desc": charge.get("desc", ""),
            }
            final_set.append(item)
    return final_set


def lambda_handler(event, context):
    """
    The api will handle listing for billing logs based on org id
    """
    auth_user = event["requestContext"].get("authorizer")
    result = get_billing_log(auth_user["userOrg"])
    return {
        "statusCode": 200,
        "body": json.dumps(result, default=str),
        "headers": get_headers(),
    }
