import boto3
from db_ops import get_db_connect

cnx = get_db_connect()

dynamo_db = boto3.resource("dynamodb", region_name="us-east-1")


def create_update_user_profile(user_data):
    """
    Add the User Details to Dynamo db.
    """
    try:
        table = dynamo_db.Table("user_pii")
        table.put_item(Item=user_data)
        print(
            f"Successfully Updated DynamoDB entry with country codes for {user_data.get('external_id','Unknown')}"
        )
    except Exception:
        print(
            f"[ERROR]: Failed to update DynamoDB entry with country codes for {user_data.get('external_id','Unknown')}"
        )


def update_patient_caregiver_pii_data(patient_caregiver_external_ids, role):
    """
    Updates PHI data for patient an caregiver with country_code for
    cell and home_tel numbers
    """
    user_pii = dynamo_db.Table("user_pii")
    for external_id in patient_caregiver_external_ids:
        try:
            response = user_pii.get_item(Key={"external_id": external_id})
            patient_data = response["Item"]
            patient_data.update(
                {
                    "cell_country_code": patient_data.get("cell_country_code", "+1"),
                    "home_tel_country_code": patient_data.get(
                        "home_tel_country_code", "+1"
                    ),
                }
            )
            create_update_user_profile(patient_data)
        except Exception:
            print(f"[ERROR]: Failed to find DynamoDB entry for {role} {external_id}")


def update_provider_cust_admin_pii_data(provider_external_ids, role):
    """
    Updates PHI data for patient an caregiver with country_code for
    cell and office_tel numbers
    """
    user_pii = dynamo_db.Table("user_pii")
    for external_id in provider_external_ids:
        try:
            response = user_pii.get_item(Key={"external_id": external_id})
            patient_data = response["Item"]
            patient_data.update(
                {
                    "cell_country_code": patient_data.get("cell_country_code", "+1"),
                    "office_tel_country_code": patient_data.get(
                        "office_tel_country_code", "+1"
                    ),
                }
            )
            create_update_user_profile(patient_data)
        except Exception:
            print(f"[ERROR]: Failed to find DynamoDB entry for {role} {external_id}")


def get_patient_list():
    """
    Returns list of patient external_ids for all patients
    """
    patient_external_ids = []
    with cnx.cursor() as cursor:
        cursor.execute("SELECT external_id from patients")
        db_patient_data = cursor.fetchall()
        for db_patient in db_patient_data:
            if db_patient[0]:
                patient_external_ids.append(db_patient[0])
        cursor.close()
    return patient_external_ids


def get_caregiver_list():
    """
    Returns list of patient external_ids for all caregivers
    """
    caregiver_external_ids = []
    with cnx.cursor() as cursor:
        cursor.execute("SELECT external_id from caregivers")
        db_caregiver_data = cursor.fetchall()
        for db_caregiver in db_caregiver_data:
            if db_caregiver[0]:
                caregiver_external_ids.append(db_caregiver[0])
        cursor.close()
    return caregiver_external_ids


def get_provider_list():
    """
    Returns list of patient external_ids for all providers
    """
    provider_internal_ids = []
    with cnx.cursor() as cursor:
        cursor.execute("SELECT external_id from providers")
        db_provider_data = cursor.fetchall()
        for db_provider in db_provider_data:
            if db_provider[0]:
                provider_internal_ids.append(db_provider[0])
        cursor.close()
    return provider_internal_ids


def get_customer_admin_list():
    """
    Returns list of patient external_ids for all customer admins
    """
    customer_admin_internal_ids = []
    with cnx.cursor() as cursor:
        cursor.execute("SELECT external_id from customer_admins;")
        db_provider_data = cursor.fetchall()
        for db_provider in db_provider_data:
            if db_provider[0]:
                customer_admin_internal_ids.append(db_provider[0])
        cursor.close()
    return customer_admin_internal_ids


def main():
    """
    This Function:
    1. Gets list of external id for all
       patients, caregivers, providers, customer admins
    2. Updates Phi data with country code values for
       the phone numbers present for user
    """
    patient_external_ids = get_patient_list()
    caregiver_external_ids = get_caregiver_list()
    provider_external_ids = get_provider_list()
    customer_admin_external_ids = get_customer_admin_list()
    print("\n...Patient List PII Data Update Start...\n")
    update_patient_caregiver_pii_data(patient_external_ids, "Patient")
    print("\n...Patient List PII Data Update End...\n")
    print("\n...Caregiver List PII Data Update Start...\n")
    update_patient_caregiver_pii_data(caregiver_external_ids, "Caregiver")
    print("\n...Caregiver List PII Data Update End...\n")
    print("\n...Provider List PII Data Update Start...\n")
    update_provider_cust_admin_pii_data(provider_external_ids, "Provider")
    print("\n...Provider List PII Data Update End...\n")
    print("\n...Customer Admin List PII Data Update Start...\n")
    update_provider_cust_admin_pii_data(customer_admin_external_ids, "Customer Admin")
    print("\n...Customer Admin List PII Data Update End...\n")
