import json

from shared import get_db_connect, get_headers, read_as_dict, read_query

connection = get_db_connect()


def get_med_duration(cnx):
    """
    This API Fetches the Medication Duration.
    """
    query = """ SELECT duration_name FROM med_duration """
    med_duration = read_query(cnx, query)
    result_set = [duration[0] for duration in med_duration]
    return result_set


def get_med_sig(cnx):
    """
    This API Fetches the Med Sig.
    """
    query = """ SELECT medsig_name FROM med_sig """
    med_sig = read_query(cnx, query)
    result_set = [sig[0] for sig in med_sig]
    return result_set


def get_med_unit(cnx):
    """
    This API Fetches the Medication Unit.
    """
    query = """ SELECT medunit_name FROM med_unit """
    med_unit = read_query(cnx, query)
    result_set = [unit[0] for unit in med_unit]
    return result_set


def get_med_info_from(cnx):
    """
    This API Fetches the Medication Info From.
    """
    query = """ SELECT infofrom_name FROM med_info_from """
    med_info_from = read_query(cnx, query)
    result_set = [info[0] for info in med_info_from]
    return result_set


def get_med_reasons(cnx):
    """
    This API Fetches the Medication Reasons.
    """
    query = """ SELECT medication_reasons FROM med_reasons WHERE entity_active = 'Y' """
    med_reasons = read_query(cnx, query)
    result_set = [reason[0] for reason in med_reasons]
    return result_set


def get_med_discontinue_reason(cnx):
    """
    This API Fetches the Medication Reasons.
    """
    query = """ SELECT discontinue_code as id, discontinue_reason FROM med_discontinue WHERE entity_active = 'Y' """
    result = read_as_dict(cnx, query)
    return [{"id": item["id"], "reason": item["discontinue_reason"]} for item in result]


def lambda_handler(event, context):
    """
    Medication Unit Handler
    """
    paths = event["path"].split("/")
    if "sig" in paths:
        result = get_med_sig(connection)
    elif "medreasons" in paths:
        result = get_med_reasons(connection)
    elif "unit" in paths:
        result = get_med_unit(connection)
    elif "info_from" in paths:
        result = get_med_info_from(connection)
    elif "duration" in paths:
        result = get_med_duration(connection)
    elif "discontinue" in paths:
        result = get_med_discontinue_reason(connection)
    else:
        result = []
    return {"statusCode": 200, "body": json.dumps(result), "headers": get_headers()}
