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
            f"Successfully Updated DynamoDB entry with stripped first and last name for {user_data.get('external_id','Unknown')}"
        )
    except Exception:
        print(
            f"[ERROR]: Failed to update DynamoDB entry with tripped first and last name for {user_data.get('external_id','Unknown')}"
        )


def update_user_pii_data(provider_external_ids):
    """
    Updates DynamoDB data for the input list of external_ids
    Strips whitespaces from first and last name property values
    """
    user_pii = dynamo_db.Table("user_pii")
    for external_id in provider_external_ids:
        try:
            response = user_pii.get_item(Key={"external_id": external_id})
            patient_data = response["Item"]
            patient_data.update(
                {
                    "first_name": str(patient_data.get("first_name", "")).strip(),
                    "last_name": str(patient_data.get("last_name", "")).strip(),
                }
            )
            create_update_user_profile(patient_data)
        except Exception:
            print(f"[ERROR]: Failed to find DynamoDB entry for Provider {external_id}")


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


def main():
    """
    This Function:
    1. Gets list of external id for all patients
    2. Updates Phi data with stripped FN and LN of existing values
    """
    patient_external_ids = get_patient_list()
    print("\n...Patient List PII Data Update Start...\n")
    update_user_pii_data(patient_external_ids)
    print("\n...Patient List PII Data Update End...\n")
    print(
        "Please run the update_hash_patient.py script to update the existing hashes for pateints in SQL DB"
    )
