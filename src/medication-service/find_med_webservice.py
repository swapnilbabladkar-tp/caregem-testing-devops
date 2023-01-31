import json

from med_utils import get_product_by_names
from shared import get_headers


def get_medication_by_name(name, max_result_set):
    """
    Fetches the medications that matches the name from a web Service.
    Returns the medication names
    """
    result = get_product_by_names(name, max_result_set)
    final_result = []
    for product in range(len(result[1])):
        product_dict = {
            "productName": result[1][product],
            "strengthsAndForms": result[2]["STRENGTHS_AND_FORMS"][product],
            "rxcuis": result[2]["RXCUIS"][product],
        }
        final_result.append(product_dict)
    return final_result


def lambda_handler(event, context):
    """
    Find Medication Handler
    """
    name = event["queryStringParameters"].get("name")
    max_result_set = event["queryStringParameters"].get("max_results", 20)
    result = get_medication_by_name(name, max_result_set)
    return {"statusCode": 200, "body": json.dumps(result), "headers": get_headers()}
