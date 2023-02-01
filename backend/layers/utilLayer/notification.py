from custom_exception import GeneralException
from notification_sqls import (
    INSERT_CARE_TEAM_NOTIFICATION,
    INSERT_MEDICATION_NOTIFICATION,
    INSERT_MESSAGE_NOTIFICATION,
    INSERT_REMOTE_VITAL_NOTIFICATION,
    INSERT_SYMPTOM_NOTIFICATION,
)
from shared import get_db_connect

cnx = get_db_connect()


def insert_to_symptom_notifications_table(
    medical_data_type,
    medical_data_id,
    patient_internal_id,
    level,
    notification_details,
    created_on,
    created_by,
    notification_status,
    notifier_internal_id,
):
    """
    Inserts row in symptom_notifications Tables based on input data
    """
    try:
        with cnx.cursor() as cursor:
            notification_param = {
                "medical_data_type": medical_data_type,
                "medical_data_id": medical_data_id,
                "patient_internal_id": patient_internal_id,
                "notifier_internal_id": notifier_internal_id,
                "level": level,
                "notification_details": notification_details,
                "created_on": created_on,
                "created_by": created_by,
                "updated_on": created_on,
                "updated_by": created_by,
                "notification_status": notification_status,
            }
            cursor.execute(INSERT_SYMPTOM_NOTIFICATION, notification_param)
        cnx.commit()
    except GeneralException as e:
        print(e)


def insert_to_message_notifications_table(
    message_id,
    channel_name,
    notifier_internal_id,
    receiver_internal_id,
    sender_internal_id,
    level,
    notification_details,
    created_on,
    created_by,
    updated_on,
    updated_by,
    notification_status,
):
    """
    Inserts row in message_notifications Tables based on input data
    """
    try:
        with cnx.cursor() as cursor:
            message_notification_params = {
                "message_id": message_id,
                "channel_name": channel_name,
                "notifier_internal_id": notifier_internal_id,
                "receiver_internal_id": receiver_internal_id,
                "sender_internal_id": sender_internal_id,
                "level": level,
                "notification_details": notification_details,
                "created_on": created_on,
                "created_by": created_by,
                "updated_on": updated_on,
                "updated_by": updated_by,
                "notification_status": notification_status,
            }
            cursor.execute(INSERT_MESSAGE_NOTIFICATION, message_notification_params)
        cnx.commit()
    except GeneralException as e:
        print(e)


def insert_to_remote_vital_notification_table(
    remote_vital_id,
    patient_internal_id,
    notifier_internal_id,
    level,
    notification_details,
    created_on,
    created_by,
    updated_on,
    updated_by,
    notification_status,
):
    """
    Inserts row in remote_vital_notifications Tables based on input data
    """
    try:
        with cnx.cursor() as cursor:
            remote_notification_params = {
                "remote_vital_id": remote_vital_id,
                "patient_internal_id": patient_internal_id,
                "notifier_internal_id": notifier_internal_id,
                "level": level,
                "notification_details": notification_details,
                "created_on": created_on,
                "created_by": created_by,
                "updated_on": updated_on,
                "updated_by": updated_by,
                "notification_status": notification_status,
            }
            cursor.execute(INSERT_REMOTE_VITAL_NOTIFICATION, remote_notification_params)
        cnx.commit()
    except GeneralException as e:
        print(e)


def insert_to_care_team_notification_table(
    ct_member_internal_id,
    patient_internal_id,
    notifier_internal_id,
    level,
    notification_details,
    created_on,
    created_by,
    updated_on,
    updated_by,
    notification_status,
):
    """
    Inserts row in care_team_notifications Tables based on input data
    """
    try:
        with cnx.cursor() as cursor:
            care_team_notification_params = {
                "ct_member_internal_id": ct_member_internal_id,
                "patient_internal_id": patient_internal_id,
                "notifier_internal_id": notifier_internal_id,
                "level": level,
                "notification_details": notification_details,
                "created_on": created_on,
                "created_by": created_by,
                "updated_on": updated_on,
                "updated_by": updated_by,
                "notification_status": notification_status,
            }
            cursor.execute(INSERT_CARE_TEAM_NOTIFICATION, care_team_notification_params)
        cnx.commit()
    except GeneralException as e:
        print(e)


def insert_to_medication_notifications_table(
    cnx,
    patient_internal_id,
    medication_row_id,
    notifier_internal_id,
    level,
    notification_details,
    created_on,
    created_by,
    updated_on,
    updated_by,
    notification_status,
):
    """
    Inserts row in medication_notifications Tables based on input data
    """
    try:
        with cnx.cursor() as cursor:
            notification_param = {
                "patient_internal_id": patient_internal_id,
                "medication_row_id": medication_row_id,
                "notifier_internal_id": notifier_internal_id,
                "level": level,
                "notification_details": notification_details,
                "created_on": created_on,
                "created_by": created_by,
                "updated_on": updated_on,
                "updated_by": updated_by,
                "notification_status": notification_status,
            }
            cursor.execute(INSERT_MEDICATION_NOTIFICATION, notification_param)
        cnx.commit()
    except GeneralException as e:
        print(e)
