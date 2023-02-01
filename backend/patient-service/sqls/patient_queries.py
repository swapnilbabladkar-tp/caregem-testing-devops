# Alert Trend Query

ALERT_TREND_QUERY = """
SELECT
    *
FROM
    mi_alert_trends
WHERE
    patient_id = %(patient_id)s
        AND most_recent_flag = '1';
"""

# Patient INFO
PATIENT_DETAILS = """
SELECT 
    *
FROM
    patients
WHERE
    internal_id = %(patient_id)s;
"""

# Patient Lab data
PATIENT_LAB_DATA = """
SELECT 
    *
FROM
    lab_data
WHERE
    patient_id = %(patient_id)s;
"""


# Patient Symptoms Query

patient_symptoms_query = """
SELECT 
    mi_symptoms.id AS mi_symptoms_id,
    mi_symptoms.patient_id AS mi_symptoms_patient_id,
    mi_symptoms.info_text AS mi_symptoms_info_text,
    mi_symptoms.info_blob AS mi_symptoms_info_blob,
    mi_symptoms.flag_read AS mi_symptoms_flag_read,
    mi_symptoms.enter_date AS mi_symptoms_enter_date,
    mi_symptoms.submitted_by AS mi_symptoms_submitted_by,
    mi_symptoms.survey_type AS mi_symptoms_survey_type,
    mi_symptoms.survey_id AS mi_symptoms_survey_id
FROM
    mi_symptoms
        INNER JOIN
    patients ON patients.internal_id = mi_symptoms.patient_id
WHERE
    patients.internal_id = %s
    AND mi_symptoms.submitted_by IS NOT NULL
ORDER BY mi_symptoms.enter_date DESC
"""

# Provider Symptoms Query

provider_symptoms_query = """
SELECT 
    mi_symptoms.id AS mi_symptoms_id,
    mi_symptoms.patient_id AS mi_symptoms_patient_id,
    mi_symptoms.info_text AS mi_symptoms_info_text,
    mi_symptoms.info_blob AS mi_symptoms_info_blob,
    mi_symptoms.flag_read AS mi_symptoms_flag_read,
    mi_symptoms.enter_date AS mi_symptoms_enter_date,
    mi_symptoms.submitted_by AS mi_symptoms_submitted_by,
    mi_symptoms.survey_type AS mi_symptoms_survey_type,
    mi_symptoms.survey_id AS mi_symptoms_survey_id,
    symptom_notifications.id AS notifications_id,
    symptom_notifications.medical_data_type AS notifications_medical_data_type,
    symptom_notifications.medical_data_id AS notifications_medical_data_id,
    symptom_notifications.patient_internal_id AS notifications_patient_internal_id,
    symptom_notifications.notifier_internal_id AS notifications_provider_internal_id,
    symptom_notifications.`level` AS notifications_level
FROM
    mi_symptoms
        INNER JOIN
    patients ON patients.internal_id = mi_symptoms.patient_id
        INNER JOIN
    networks ON networks._patient_id = patients.id
        INNER JOIN
    providers ON providers.internal_id = networks.user_internal_id
        LEFT OUTER JOIN
    symptom_notifications ON symptom_notifications.medical_data_id = mi_symptoms.id
        AND symptom_notifications.patient_internal_id = patients.internal_id
        AND symptom_notifications.notifier_internal_id = providers.internal_id
WHERE
    patients.internal_id = %s
        AND providers.internal_id = %s
    AND mi_symptoms.submitted_by IS NOT NULL
ORDER BY symptom_notifications.`level` DESC
"""

caregiver_symptoms_query = """
SELECT 
    mi_symptoms.id AS mi_symptoms_id,
    mi_symptoms.patient_id AS mi_symptoms_patient_id,
    mi_symptoms.info_text AS mi_symptoms_info_text,
    mi_symptoms.info_blob AS mi_symptoms_info_blob,
    mi_symptoms.flag_read AS mi_symptoms_flag_read,
    mi_symptoms.enter_date AS mi_symptoms_enter_date,
    mi_symptoms.submitted_by AS mi_symptoms_submitted_by,
    mi_symptoms.survey_type AS mi_symptoms_survey_type,
    mi_symptoms.survey_id AS mi_symptoms_survey_id
FROM
    mi_symptoms
        INNER JOIN
    patients ON patients.internal_id = mi_symptoms.patient_id
        INNER JOIN
    networks ON networks._patient_id = patients.id
        INNER JOIN
    caregivers ON caregivers.internal_id = networks.user_internal_id
WHERE
    patients.internal_id = %s
        AND caregivers.internal_id = %s
        AND mi_symptoms.submitted_by IS NOT NULL
GROUP BY mi_symptoms.id
ORDER BY mi_symptoms.enter_date DESC
"""

# Patient Utilization Query

PATIENT_UTILIZATION_QUERY = """
SELECT 
    *
FROM
    utilization
WHERE
    patient_id = %(patient_id)s;
"""

PATIENT_LAST_SURVEY = """
SELECT 
    survey_type, MAX(enter_date) AS max_1
FROM
    mi_symptoms
WHERE
    patient_id = %(patient_id)s
GROUP BY survey_type , patient_id;
"""
# Patient Links query
PATIENT_LINK_QUERY = """
SELECT 
    id, `key` AS link_key, link, category
FROM
    link
WHERE
    category = %(category)s
"""
# Patient risk profile
PATIENT_RISK_PROFILE = """
SELECT 
    *
FROM
    risk_profile
WHERE
    patient_id = %(patient_id)s;
"""

PROVIDER_PATIENT_NETWORK = """
SELECT 
    patients.activated AS activated,
    patients.id AS id,
    patients.username AS username,
    patients.external_id AS external_id,
    patients.internal_id AS internal_id,
    patients.remote_monitoring AS remote_monitoring
FROM
    networks
        INNER JOIN
    patients ON patients.id = networks._patient_id
        LEFT JOIN
    code_assigned ON (True = %(j_code_assign)s
        AND code_assigned.patient_internal_id = patients.internal_id)
WHERE
    networks.user_internal_id =  %(internal_id)s
        AND (%(j_code_assign)s is NULL OR assigned_code IN %(codes)s)
        AND (%(rm_enabled)s is NULL OR remote_monitoring=%(rm_enabled)s)
GROUP BY patients.id
"""

PATIENT_PROVIDER_NETWORK = """
SELECT 
    networks.user_internal_id AS user_internal_id,
    networks.id AS networks_id,
    providers.id AS id,
    providers.external_id AS external_id,
    providers.internal_id AS internal_id,
    providers.`role` AS `role`,
    providers.`group` AS `group`,
    providers.degree AS degree,
    providers.specialty AS specialty
FROM
    networks
        INNER JOIN
    patients ON patients.id = networks._patient_id
        JOIN
    providers ON providers.internal_id = networks.user_internal_id
WHERE
    networks._patient_id = %(patient_id)s
        AND (%(n_roles)s is NULL OR providers.`role` IN %(roles)s)
        AND (%(specialty)s is NULL OR providers.specialty LIKE %(specialty)s);
"""

APPOINTMENT_QUERY = """
SELECT 
    appointments.id AS id,
    appointments.patient_internal_id AS patient_internal_id,
    appointments.provider_internal_id AS provider_internal_id,
    appointments.date_time AS date_time,
    appointments.active AS active
FROM
    appointments
WHERE
    appointments.provider_internal_id = %(provider_internal_id)s
        AND appointments.patient_internal_id IN %(patient_id)s
        AND appointments.active = 1
"""

PROVIDER_NOTIFICATIONS = """
SELECT notifications_table.patient_internal_id AS patient_internal_id,
       notifications_table.medical_data_type   AS medical_data_type,
       Max(notifications_table.`level`)        AS max_1
FROM   (SELECT notifier_internal_id,
               `level`,
               patient_internal_id,
               medical_data_type,
               notification_status
        FROM   symptom_notifications
        UNION
        SELECT notifier_internal_id,
               `level`,
               patient_internal_id,
               "care_team",
               notification_status
        FROM   care_team_notifications
        UNION
        SELECT notifier_internal_id,
               `level`,
               patient_internal_id,
               "medications",
               notification_status
        FROM   medication_notifications
        UNION
        SELECT notifier_internal_id,
               `level`,
               patient_internal_id,
               "remote_vitals",
               notification_status
        FROM   remote_vital_notifications) AS notifications_table
       INNER JOIN (SELECT internal_id,
                          external_id
                   FROM   providers
                   UNION
                   SELECT internal_id,
                          external_id
                   FROM   caregivers) AS union_table
               ON union_table.internal_id =
                  notifications_table.notifier_internal_id
WHERE  union_table.internal_id = %(notifier_internal_id)s
       AND notifications_table.notification_status = 1
GROUP  BY notifications_table.medical_data_type,
          notifications_table.patient_internal_id; 
"""
