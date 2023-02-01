import json
import logging
import re
from datetime import datetime
from urllib.parse import quote_plus

import boto3
from custom_exception import GeneralException
from shared import get_db_connect, get_headers, get_phi_data, read_as_dict
from sqls.patient_queries import (
    PATIENT_DETAILS,
    PATIENT_LAST_SURVEY,
    PATIENT_LINK_QUERY,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
dynamodb = boto3.resource("dynamodb")

connection = get_db_connect()


def remove_special_chars(string):
    """
    Returns input string with special characters removed
    and case changed to lower case
    """
    if not string:
        return ""
    return re.sub(r"\W+", "", string.lower())


def get_last_survey_dict(cnx, patient_id):
    """
    Returns latest symptpom type and the date reported for the patient
    """
    params = {"patient_id": patient_id}
    last_survey_dict = read_as_dict(cnx, PATIENT_LAST_SURVEY, params)
    return {remove_special_chars(key): date for (key, date) in last_survey_dict}


def get_survey_links(cnx, category, patient_id):
    """
    Returns list of links for the Symptom forms for the patient to report symtpoms
    """
    try:
        patient = read_as_dict(cnx, PATIENT_DETAILS, {"patient_id": patient_id})
        if patient:
            patient = patient[0]
        else:
            return 400, "Patient Not found"
        dynamodb_data = get_phi_data(patient["external_id"], dynamodb)
        results = read_as_dict(cnx, PATIENT_LINK_QUERY, {"category": category})
        last_survey_dict = get_last_survey_dict(cnx, patient_id)
        datetime_now = datetime.now()
        final_links = []
        for result in results:
            patient_email = quote_plus(dynamodb_data["email"]).strip()
            url_link = str(result["link"]).strip()
            clean_key = remove_special_chars(result["link_key"])
            last_survey_date = (
                last_survey_dict[clean_key] if clean_key in last_survey_dict else None
            )
            days_since_last_survey = (
                (datetime_now - last_survey_date).days if last_survey_date else None
            )
            highlighted = (
                1
                if (
                    (days_since_last_survey is not None)
                    and (days_since_last_survey <= 15)
                )
                else 0
            )
            final_links.append(
                {
                    "key": str(result["link_key"]).strip(),
                    "link": f"{url_link}{patient_email}",
                    "highlighted": highlighted,
                }
            )
        return 200, final_links
    except GeneralException as err:
        logger.exception(err)
        return 500, err


def lambda_handler(event, context):
    """
    The api will handle getting survey links for a patient
    """
    category = event["pathParameters"].get("type")
    patient_internal_id = event["pathParameters"].get("patient_internal_id")
    status_code, user_result = get_survey_links(
        connection, category, patient_internal_id
    )
    return {
        "statusCode": status_code,
        "body": json.dumps(user_result),
        "headers": get_headers(),
    }
