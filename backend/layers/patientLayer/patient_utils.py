from itertools import groupby

from medical_info import MedicalType
from shared import get_phi_data, read_as_dict, read_query


def get_patient_details(cnx, patient_id, org_id):
    """
    Get the Patient Details along with Newtork and Device Info
    """
    pat_query = """ SELECT activated,
                           external_id,
                           id,
                           internal_id,
                           ref_uid,
                           remote_monitoring,
                           username
                    FROM   patients
                    WHERE  id = %s
                        AND activated = 1 """
    device_query = """ SELECT imei,
                              DATE_FORMAT(start_date, '%%d-%%m-%%Y %%h:%%m:%%s') as start_date
                        FROM  device_pairing
                        WHERE patient_internal_id = %s
                              AND active = 'Y'
                        limit 1"""
    patient_details = read_as_dict(cnx, pat_query, (patient_id))
    if patient_details:
        patient_details = patient_details[0]
        phi_data = get_phi_data(patient_details["external_id"])
        patient_details.update(phi_data)
        device_details = read_as_dict(
            cnx, device_query, (patient_details["internal_id"])
        )
        patient_details.update(
            {
                "name": phi_data.get("first_name") + " " + phi_data.get("last_name"),
                "first_name": phi_data.get("first_name"),
                "last_name": phi_data.get("last_name"),
            }
        )
        if device_details:
            patient_details.update(device_details[0])
        else:
            patient_details.update({"device_pairing": None, "start_date": None})
        return patient_details
    return []


def get_chat_summary_base_query():
    """
    Get older chat history if available.
    Note to devs: Not to be messed up with.
    """
    query = """
            SELECT
            chat.id AS chat_id,
            chat.connected_user_id AS chat_connected_user_id,
            chat.`role` AS chat_role,
            chat.chat_id AS chat_id,
            chat._patient_id AS patientId,
            chat.internal_id AS internal_id,
            chat.external_id AS patient_external_id,
            connected_user.username AS username,
            connected_user.internal_id AS id,
            connected_user.external_id AS external_id,
            connected_user.`role` AS role,
            connected_user.specialty AS specialty,
            msg.id AS msg_id,
            msg.msg_type AS msg_type,
            msg.sender_int_id AS sender_int_id,
            msg.receiver_int_id AS receiver_int_id,
            msg.patient_int_id AS patient_int_id,
            msg.`action` AS action,
            msg.critical AS critical,
            msg.content AS lastMessage,
            msg.timestamp AS timestamp,
            msg.chat_id AS msg_chat_id,
            msg.`read` AS `read`,
            msg.unread_count AS unreadMessages
        FROM
            (SELECT
                chats.id AS id,
                    chats.connected_user_id AS connected_user_id,
                    chats.`role` AS `role`,
                    chats.chat_id AS chat_id,
                    chats._patient_id AS _patient_id,
                    patients.internal_id AS internal_id,
                    patients.external_id AS external_id
            FROM
                chats
            LEFT OUTER JOIN patients ON chats._patient_id = patients.id
            WHERE
                chats.chat_id IN (SELECT
                        chats.chat_id
                    FROM
                        chats
                    WHERE
                        chats.connected_user_id = %s)
                    AND chats.connected_user_id != %s) AS chat
                INNER JOIN
            (SELECT
                anon_4.username AS username,
                    anon_4.internal_id AS internal_id,
                    anon_4.external_id AS external_id,
                    anon_4.`role` AS `role`,
                    anon_4.specialty AS specialty,
                    anon_4.degree AS degree
            FROM
                (SELECT
                patients.username AS username,
                    patients.internal_id AS internal_id,
                    patients.external_id AS external_id,
                    '' AS `role`,
                    '' AS specialty,
                    '' AS degree
            FROM
                patients UNION SELECT
                providers.username AS username,
                    providers.internal_id AS internal_id,
                    providers.external_id AS external_id,
                    providers.`role` AS `role`,
                    providers.specialty AS specialty,
                    providers.degree AS degree
            FROM
                providers UNION SELECT
                caregivers.username AS username,
                    caregivers.internal_id AS internal_id,
                    caregivers.external_id AS external_id,
                    'caregiver' AS `role`,
                    '' AS specialty,
                    '' AS degree
            FROM
                caregivers) AS anon_4) AS connected_user ON connected_user.username = chat.connected_user_id
                INNER JOIN
            (SELECT
                anon_5.id AS id,
                    anon_5.msg_type AS msg_type,
                    anon_5.sender_int_id AS sender_int_id,
                    anon_5.receiver_int_id AS receiver_int_id,
                    anon_5.patient_int_id AS patient_int_id,
                    anon_5.`action` AS `action`,
                    anon_5.critical AS critical,
                    anon_5.content AS content,
                    anon_5.timestamp AS timestamp,
                    anon_5.chat_id AS chat_id,
                    anon_5.`read` AS `read`,
                    anon_6.unread_count AS unread_count
            FROM
                (SELECT
                messages.id AS id,
                    messages.msg_type AS msg_type,
                    messages.sender_int_id AS sender_int_id,
                    messages.receiver_int_id AS receiver_int_id,
                    messages.patient_int_id AS patient_int_id,
                    messages.`action` AS `action`,
                    messages.critical AS critical,
                    messages.content AS content,
                    messages.timestamp AS timestamp,
                    messages.chat_id AS chat_id,
                    messages.`read` AS `read`
            FROM
                messages
            WHERE
                (messages.chat_id , messages.timestamp) IN (SELECT
                        messages.chat_id AS chat_id,
                            MAX(messages.timestamp) AS timestamp
                    FROM
                        messages
                    GROUP BY messages.chat_id)) AS anon_5
            LEFT OUTER JOIN (SELECT
                messages.chat_id AS chat_id,
                    COUNT(messages.`read`) AS unread_count
            FROM
                messages
            WHERE
                messages.`read` = 0
            GROUP BY messages.chat_id) AS anon_6 ON anon_5.chat_id = anon_6.chat_id) AS msg ON msg.chat_id = chat.chat_id
            """
    return query


def get_notification_level_from_network(cnx, internal_id, pat_int_id=None):
    """
    This function returns a list of dict with the following properties:
    1. patient_id - ID of the patient
    2. medical_data_level - list of int with level of notification in the
                            same order as ordered_list in MedicalType class
    3. medical_data_obj - list of dict with id, desc and level
                          of the notification for level data above
    4. notification_level - max notification level for the patient
    """
    query = """
            SELECT symptom_notifications.patient_internal_id AS patient_internal_id,
                   symptom_notifications.medical_data_type   AS medical_data_type,
                   Max(symptom_notifications.`LEVEL`)    AS max_1
            FROM   symptom_notifications
                   inner join providers
                           ON providers.internal_id = symptom_notifications.notifier_internal_id
            WHERE  providers.internal_id = %s
            GROUP  BY symptom_notifications.medical_data_type,
                      symptom_notifications.patient_internal_id
            """
    if pat_int_id:
        query = """
            SELECT symptom_notifications.patient_internal_id AS patient_internal_id,
                   symptom_notifications.medical_data_type   AS medical_data_type,
                   Max(symptom_notifications.`LEVEL`)    AS max_1
            FROM   symptom_notifications
                   inner join providers
                           ON providers.internal_id = symptom_notifications.notifier_internal_id
            WHERE  providers.internal_id = %s
            AND symptom_notifications.patient_internal_id = %s
            GROUP  BY symptom_notifications.medical_data_type,
                      symptom_notifications.patient_internal_id
            """
        notification_tuple_list = list(
            read_query(cnx, query, (internal_id, pat_int_id))
        )
    else:
        notification_tuple_list = list(read_query(cnx, query, (internal_id)))
    medical_data_list = [0] * MedicalType.get_size()
    # The following black magic converts the notification_tuple_list to a list of dicts in format:
    #
    #   {
    #       "patient_id": pat_id,
    #       "notification_level": {
    #           medical_data_type: notification_level,
    #           medical_data_type: notification_level,
    #           ...
    #       }
    #   }
    #
    grouped_notif_list = [
        {
            "patient_id": pat_id,
            "notification_level": {
                med_index: max([flag[1] for flag in flag_list])
                for med_index, flag_list in groupby(
                    [(med_type[1], med_type[2]) for med_type in med_type_tuple],
                    lambda med_type_item: med_type_item[0],
                )
            },
        }
        for pat_id, med_type_tuple in groupby(
            notification_tuple_list, lambda notif_tuple_item: notif_tuple_item[0]
        )
    ]
    notification_list = []
    for notif in grouped_notif_list:
        med_list = list(medical_data_list)
        med_list_obj = []
        for index, value in enumerate(MedicalType.ordered_list):
            med_list_obj.append({"id": index, "desc": value, "level": 0})
        level_dict = notif["notification_level"]
        for key in level_dict.keys():
            med_item_index = MedicalType.get_index(key)
            med_list[med_item_index] = level_dict[key]
            med_list_obj[med_item_index]["level"] = level_dict[key]
        notification_list.append(
            {
                "patient_id": notif["patient_id"],
                "medical_data_level": med_list,
                "medical_data_obj": med_list_obj,
                "notification_level": max(med_list),
            }
        )
    return notification_list
