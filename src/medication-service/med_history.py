import json
import logging

import boto3
from custom_exception import GeneralException
from med_utils import get_external_id_form_internal_id, get_product_name_on_rxcui
from shared import get_db_connect, get_headers, get_phi_data_list, read_as_dict
from sqls.medication import med_base_query

dynamodb = boto3.resource("dynamodb")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()


def find_medication_by_ingredient_list(cnx, patient_id, ingredients):
    """
    Find the list of medications having the same ingredients
    """
    query = med_base_query
    if ingredients:
        conditions = " OR ".join(
            [
                "Lower(medication.ingredient) like " + "'%%" + ing["Name"] + "%%'"
                for ing in ingredients
            ]
        )
        query += " AND " + "(" + conditions + ")"
    medication = read_as_dict(
        cnx, query, {"patient_id": patient_id, "status": tuple(["M", "S"])}
    )
    return medication


def get_med_history(cnx, patient_id, rxcui_id):
    """
    This API Fetches the Medication History for a drug.
    """
    rxcui_history = get_product_name_on_rxcui(rxcui_id)["rxcuiStatusHistory"].get(
        "definitionalFeatures"
    )
    ingredients = [
        {
            "Identifier": rx["activeIngredientRxcui"],
            "Name": rx["activeIngredientName"],
        }
        for rx in rxcui_history["ingredientAndStrength"]
    ]
    logger.info(ingredients)
    med_hist = find_medication_by_ingredient_list(cnx, patient_id, ingredients)
    if not med_hist:
        return []
    internal_ids = set()
    for med in med_hist:
        internal_ids.update([med["ModifiedBy"], med["CreatedBy"]])
    internal_ids = list(internal_ids)
    ext_int_id_mapping = get_external_id_form_internal_id(cnx, internal_ids)
    external_ids = list(ext_int_id_mapping.values())
    phi_data = get_phi_data_list(external_ids, dynamodb)
    try:
        for med in med_hist:
            entered_by = phi_data[ext_int_id_mapping[med["CreatedBy"]]]
            modified_by = phi_data[ext_int_id_mapping[med["ModifiedBy"]]]
            med["CreatedBy"] = (
                entered_by.get("first_name") + " " + entered_by.get("last_name")
            )
            med["ModifiedBy"] = (
                modified_by.get("first_name") + " " + modified_by.get("last_name")
            )
            med["MedReasons"] = (
                med["MedReasons"].split(",") if med["MedReasons"] else []
            )
            med["DiscontinuedReason"] = (
                json.loads(med["DiscontinuedReason"])
                if med["DiscontinuedReason"]
                else []
            )
    except KeyError as err:
        logger.exception(err)
    except GeneralException as err:
        logger.exception(err)
    return med_hist


def lambda_handler(event, context):
    """
    Medication drug history Handler
    """
    patient_id = event["pathParameters"].get("patient_id")
    rxcui_id = event["pathParameters"].get("rxcui_id")
    return {
        "statusCode": 200,
        "body": json.dumps(get_med_history(connection, patient_id, rxcui_id)),
        "headers": get_headers(),
    }
