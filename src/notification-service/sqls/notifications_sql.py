PATIENT_SYMPTOM_NOTIFICATIONS_BASE_QUERY = """SELECT *
FROM   symptom_notifications
WHERE  patient_internal_id = %(user_internal_id)s
AND notifier_internal_id = %(logged_in_user_internal_id)s"""

NOTIFIER_SYMPTOM_NOTIFICATIONS_BASE_QUERY = """SELECT *
FROM   symptom_notifications
WHERE  notifier_internal_id = %(user_internal_id)s"""


USER_LIST = """SELECT internal_id,
       external_id,
       degree 
FROM   providers 
WHERE  internal_id IN %(user_id_string_list)s 
UNION 
SELECT internal_id,
       external_id,
       null 
FROM   patients 
WHERE  internal_id IN %(user_id_string_list)s 
UNION 
SELECT internal_id,
       external_id,
       null 
FROM   caregivers 
WHERE  internal_id IN %(user_id_string_list)s
UNION 
SELECT internal_id,
       external_id,
       null 
FROM   customer_admins 
WHERE  internal_id IN %(user_id_string_list)s
"""

UPDATE_SYMPTOMS_NOTIFICATION = """UPDATE symptom_notifications
SET    notification_status = %(notification_status)s,
       updated_by = %(logged_in_user_internal_id)s,
       updated_on = %(current_time)s
WHERE  id = %(notification_id)s"""

GET_MESSAGE_NOTIFICATIONS = """SELECT *
FROM   message_notifications
WHERE  notifier_internal_id = %(user_internal_id)s"""

UPDATE_MESSAGE_NOTIFICATION = """UPDATE message_notifications
SET    notification_status = %(notification_status)s,
       updated_by = %(logged_in_user_internal_id)s,
       updated_on = %(current_time)s
WHERE  id = %(notification_id)s"""

PATIENT_REMOTE_VITAL_NOTIFICATIONS_BASE_QUERY = """SELECT *
FROM   remote_vital_notifications
WHERE  patient_internal_id = %(user_internal_id)s
AND notifier_internal_id = %(logged_in_user_internal_id)s"""

NOTIFIER_REMOTE_VITAL_NOTIFICATIONS_BASE_QUERY = """SELECT *
FROM   remote_vital_notifications
WHERE  notifier_internal_id = %(user_internal_id)s"""

UPDATE_REMOTE_VITAL_NOTIFICATION = """UPDATE remote_vital_notifications
SET    notification_status = %(notification_status)s,
       updated_by = %(logged_in_user_internal_id)s,
       updated_on = %(current_time)s
WHERE  id = %(notification_id)s"""

PATIENT_CARE_TEAM_NOTIFICATIONS_BASE_QUERY = """SELECT *
FROM   care_team_notifications
WHERE  patient_internal_id = %(user_internal_id)s
AND notifier_internal_id = %(logged_in_user_internal_id)s"""

NOTIFIER_CARE_TEAM_NOTIFICATIONS_BASE_QUERY = """SELECT *
FROM   care_team_notifications
WHERE  notifier_internal_id = %(user_internal_id)s"""

UPDATE_CARE_TEAM_NOTIFICATION = """UPDATE care_team_notifications
SET    notification_status = %(notification_status)s,
       updated_by = %(logged_in_user_internal_id)s,
       updated_on = %(current_time)s
WHERE  id = %(notification_id)s"""

PATIENT_MEDICATION_NOTIFICATIONS_BASE_QUERY = """SELECT *
FROM   medication_notifications
WHERE  patient_internal_id = %(user_internal_id)s
AND notifier_internal_id = %(logged_in_user_internal_id)s"""

NOTIFIER_MEDICATION_NOTIFICATIONS_BASE_QUERY = """SELECT *
FROM   medication_notifications
WHERE  notifier_internal_id = %(user_internal_id)s"""

UPDATE_MEDICATION_NOTIFICATION = """UPDATE medication_notifications
SET    notification_status = %(notification_status)s,
       updated_by = %(logged_in_user_internal_id)s,
       updated_on = %(current_time)s
WHERE  id = %(notification_id)s"""

GET_NOTIFIER_ID_FOR_NOTFICIATION = """
SELECT notifier_internal_id
FROM {0}
WHERE id = %(notification_id)s
"""
