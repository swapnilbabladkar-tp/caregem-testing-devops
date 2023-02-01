import json
import logging

from shared import get_db_connect, get_headers, read_as_dict

logger = logging.getLogger(__name__)

cnx = get_db_connect()


def get_diagnose_code_list():
    """
    Get the Diagnosis Code List
    """
    query = """ SELECT abbreviated_desc AS `desc`,
                    code_detail.code AS code,
                    code_detail.DETAIL_DESC AS detail_desc
                FROM   code_detail
                WHERE  code_detail.code_type = 'ICD10' """
    return read_as_dict(cnx, query)


def get_charge_code_list():
    """
    Get the Charge Code List
    """
    query = """ SELECT abbreviated_desc AS `desc`,
                    code_detail.code AS code,
                    code_detail.DETAIL_DESC AS detail_desc
                FROM   code_detail
                WHERE  code_detail.code_type = 'BILLING' """
    return read_as_dict(cnx, query)


def lambda_handler(event, context):
    """
    Handler Function
    """
    if "charge" in event["path"].split("/"):
        result = get_charge_code_list()
    elif "diagnose" in event["path"].split("/"):
        result = get_diagnose_code_list()
    return {"statusCode": 200, "body": json.dumps(result), "headers": get_headers()}
