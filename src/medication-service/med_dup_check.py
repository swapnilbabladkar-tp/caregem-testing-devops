import json
import logging

from med_utils import get_product_name_on_rxcui, med_dup_check
from shared import get_db_connect, get_headers

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()

unit_mapping = {
    "Oral Capsule": "cap",
    "Oral Tablet": "tab",
}


def get_unit_using_den_num_formula(ingredient_list):
    """
    Returns appropriate unit for medication based in input ingredient list
    """
    numerator_unit = ingredient_list[0]["numeratorUnit"]
    denominator_unit = ingredient_list[0]["denominatorUnit"]
    unit = ""
    if denominator_unit == "ML":
        unit = "ml"
    elif numerator_unit == "MG" and denominator_unit == "ACTUATE":
        unit = "Puff"
    elif numerator_unit == "UNT" and denominator_unit == "ACTUATE":
        unit = "spray"
    elif denominator_unit == "1" and numerator_unit == "MG":
        unit = "grams" if (int(ingredient_list[0]["numeratorValue"]) > 1000) else "mg"
    return unit


def dup_check(cnx, patient_id, product_id):
    """
    Check for duplicate Medications
    """
    response_dict = {}
    data = get_product_name_on_rxcui(product_id)
    try:
        ingredient_list = data["rxcuiStatusHistory"]["definitionalFeatures"][
            "ingredientAndStrength"
        ]
    except KeyError:
        ingredient_list = []
        logger.info("Product Id Doesn't Exists")

    ingredients = []
    for rxu in ingredient_list:
        ingredient = {
            "Identifier": rxu["activeIngredientRxcui"],
            "Name": rxu["activeIngredientName"],
        }
        ingredients.append(ingredient)

    dose_form_name = data["rxcuiStatusHistory"]["definitionalFeatures"][
        "doseFormConcept"
    ][0]["doseFormName"]
    if "doseFormConcept" in data["rxcuiStatusHistory"][
        "definitionalFeatures"
    ].keys() and (
        "oral solution" not in dose_form_name.lower()
        and "oral liquid" not in dose_form_name.lower()
    ):
        if "topical" in dose_form_name.lower():
            unit = ""
        elif dose_form_name in ["Oral Capsule", "Oral Tablet"]:
            unit = unit_mapping[dose_form_name]
        elif "Ophthalmic" in dose_form_name:
            unit = "drops"
        elif "Powder" in dose_form_name:
            unit = "pack"
        else:
            unit = get_unit_using_den_num_formula(ingredient_list)
    else:
        unit = get_unit_using_den_num_formula(ingredient_list)
    meds_dict = {
        "ProductId": data["rxcuiStatusHistory"]["attributes"]["rxcui"],
        "ProductShortName": data["rxcuiStatusHistory"]["attributes"]["name"],
        "ProductLongName": data["rxcuiStatusHistory"]["attributes"]["name"],
        "Ingredient": ingredients,
        "UnitCode": unit if unit else "",
        "Status": "A",
    }
    dup_dict = med_dup_check(cnx, patient_id, ingredients, True)
    response_dict["PatientId"] = patient_id
    response_dict["Medication"] = meds_dict
    response_dict["Duplication"] = dup_dict
    return response_dict


def lambda_handler(event, context):
    """
    Medication Dup Check Handler
    """
    patient_id = event["pathParameters"].get("patient_id")
    product_id = event["pathParameters"].get("rxcui_id")
    return {
        "statusCode": 200,
        "body": json.dumps(dup_check(connection, patient_id, product_id)),
        "headers": get_headers(),
    }
