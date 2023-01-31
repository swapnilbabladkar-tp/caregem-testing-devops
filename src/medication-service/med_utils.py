import os

import requests
from dotenv import load_dotenv
from shared import read_as_dict, read_query

load_dotenv()


clinical_table_url = os.getenv("CLINICALTABLES_URL")
rxcui_url = os.getenv("RXCUIS_URL")


def get_product_name_on_rxcui(rxcui):
    """
    Get the product names on rxcuis
    Request params: rxcui id
    """
    url = rxcui_url.format(rxcui=str(rxcui))
    try:
        response = requests.get(url, timeout=5)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    return response.json()


def get_product_by_names(name, max_results):
    """
    This lambda fetches the medications from third party url based on the names.
    Request params: names, max_count
    Response : Medication names, ruxcii, strength_and_form
    """
    url = clinical_table_url
    url = url + name + "&maxList=" + str(max_results)
    try:
        response = requests.get(url, timeout=5)
    except requests.exceptions.RequestException as e:
        raise SystemExit(e)
    return response.json()


def get_ingredients_by_internal_id(cnx, patient_id, ingredient_name):
    """
    Returns list of medications having same ingredient for a given internal ID.
    """
    condition = "%" + ingredient_name + "%"
    query = """ SELECT product_id, product_short_name
                FROM medication
                WHERE patient_internal_id = %s
                AND medication.`status` = 'A'
                AND Lower(medication.ingredient) like %s"""
    result = read_as_dict(cnx, query, (patient_id, condition))
    return result if result else []


def get_external_id_form_internal_id(cnx, internal_ids):
    """
    Get the external ids from internal ID's as dict
    """
    format_str = ",".join(["%s"] * len(internal_ids))
    mapping_dict = {}
    for user in ["patients", "providers", "caregivers"]:
        query = """
                SELECT external_id, internal_id
                FROM {user}
                WHERE internal_id IN ({format_str})
                """.format(
            user=user, format_str=format_str
        )
        result_set = read_query(cnx, query, (tuple(internal_ids)))
        mapping_dict.update({id[1]: id[0] for id in result_set})
    return mapping_dict


def med_dup_check(cnx, patient_id, ingredient_list, is_check):
    """
    Returns the list of duplication list for a given medication
    """
    dup_list = []

    for ingredient in ingredient_list:
        dup_med = get_ingredients_by_internal_id(cnx, patient_id, ingredient["Name"])
        if is_check:
            dup_list.extend(
                [
                    {
                        "ProductId": dup.get("product_id"),
                        "ProductName": dup.get("product_short_name"),
                    }
                    for dup in dup_med
                ]
            )
        else:
            if len(dup_med) > 1:
                dup_list.extend(
                    [
                        {
                            "ProductId": dup.get("product_id"),
                            "ProductName": dup.get("product_short_name"),
                        }
                        for dup in dup_med
                    ]
                )
    return dup_list
