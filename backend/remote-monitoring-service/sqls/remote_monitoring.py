GET_PHYSICIAN_WITH_RM_ENABLED = """
SELECT 
    providers.id,
    providers.username,
    providers.activated,
    providers.name,
    providers.internal_id,
    providers.`role`,
    providers.`group`,
    providers.specialty,
    providers.remote_monitoring,
    providers.billing_permission
FROM
    providers
        JOIN
    provider_org ON providers.id = provider_org.providers_id
WHERE
    provider_org.organizations_id = %(org_id)s
        AND providers.`role` = 'physician'
        AND providers.remote_monitoring = 'Y'
"""

GET_DEVICE_DETAILS = """
SELECT 
    *
FROM
    device_pairing
WHERE
    patient_internal_id = %(patient_id)s;
"""

GET_CONNECTED_PROVIDERS_WITH_PATIENT = """
SELECT 
    providers.id,
    providers.username,
    providers.activated,
    providers.name,
    providers.internal_id,
    providers.`role`,
    providers.`group`,
    providers.specialty,
    providers.remote_monitoring,
    providers.billing_permission
FROM
    providers
        JOIN
    networks ON providers.internal_id = networks.user_internal_id
        JOIN
    provider_org ON providers.id = provider_org.providers_id
WHERE
    networks._patient_id = %(patient_id)s
        AND provider_org.organizations_id = %(org_id)s;
"""
GET_BILLING_DATE_OF_SERVICE = """
SELECT 
    billing_charge_code, date_of_service, provider_name
FROM
    billing_detail
WHERE
    billing_detail.patient_internal_id = %(patient_id)s
        AND billing_detail.`status` = 'Approve'
    AND (%(code_nine_four)s is NULL OR (billing_detail.date_of_service >= %(start_dt)s 
         AND billing_detail.date_of_service <= %(end_dt)s))
ORDER BY billing_detail.date_of_service DESC;
"""

GET_CALL_DURATION = """
SELECT 
    call_logs.id, call_logs.start_timestamp, call_logs.duration
FROM
    call_logs
WHERE
    call_logs.patient_internal_id = %(patient_id)s
        AND call_logs.provider_internal_id IN %(prv_ids)s
        AND call_logs.start_timestamp >= %(start_dt)s
        AND call_logs.start_timestamp <= %(end_dt)s ;
"""

GET_BILLING_DETAIL = """
SELECT 
    billing_charge_code,
    DATE_FORMAT(date_of_service, '%%a, %%d %%b %%Y %%T') AS date_of_service,
    provider_name,
    billing_detail.`status`
FROM
    billing_detail
WHERE
    billing_detail.patient_internal_id = %(patient_id)s
        AND billing_detail.date_of_service >= %(start_dt)s
        AND billing_detail.date_of_service <= %(end_dt)s
        AND billing_detail.`status` = 'Approve'
"""

GET_DEVICE_READING_COUNT = """
SELECT 
    COUNT(DISTINCT(reading_date)) AS reading_count
FROM
    device_pairing_view
WHERE
    reading_date >= %(start_dt)s
        AND reading_date <= %(end_dt)s
        AND patient_internal_id = %(patient_id)s;
"""

GET_PROVIDER_NETWORK = """
SELECT 
    patients.activated,
    patients.id,
    patients.external_id,
    patients.internal_id,
    patients.remote_monitoring
FROM
    patients
        INNER JOIN
    networks ON patients.id = networks._patient_id
WHERE
    networks.user_internal_id = %(provider_id)s
        AND patients.remote_monitoring = 'Y';
"""

REMOTE_BILLING_PROVIDERS = """
SELECT 
    providers.id,
    providers.activated,
    providers.name,
    providers.internal_id,
    providers.`role`,
    providers.`group`,
    providers.specialty,
    providers.remote_monitoring,
    providers.billing_permission
FROM
    providers
        JOIN
    provider_org ON providers.id = provider_org.providers_id
WHERE
    provider_org.organizations_id = %(org_id)s
        AND providers.billing_permission = 'Y'
        AND providers.remote_monitoring = 'Y';
"""
