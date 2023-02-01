ALL_NETWORK_SAME_PATIENT = """
SELECT DISTINCT
    networks.user_internal_id AS internal_id
FROM
    networks
WHERE
    networks._patient_id IN (SELECT
            networks._patient_id
        FROM
            networks
        WHERE
            networks.user_internal_id = %(user_id)s);
"""

LIST_PROVIDERS = """
SELECT
    providers.activated AS activated,
    providers.id AS id,
    providers.username AS username,
    providers.name AS name,
    providers.external_id AS external_id,
    providers.internal_id AS internal_id,
    providers.`ROLE` AS role,
    providers.specialty AS specialty,
    providers.`group` AS grp,
    providers.degree AS degree,
    providers.alert_receiver AS alert_receiver,
    providers.remote_monitoring AS remote_monitoring,
    providers.billing_permission AS billing_permission
FROM
    providers
        JOIN
    provider_org ON providers.id = provider_org.providers_id
WHERE
    (
        provider_org.organizations_id IN %(org_ids)s
        OR providers.internal_id IN %(connected_user_internal_ids)s
    )
    AND providers.internal_id != %(internal_id)s
    AND providers.role = %(role)s
    AND (%(specialty)s is NULL OR providers.specialty LIKE %(specialty)s);
"""
GET_APPOINTMENT = """
SELECT
    appointments.id AS id,
    appointments.patient_internal_id AS patient_internal_id,
    appointments.provider_internal_id AS provider_internal_id,
    appointments.date_time AS date_time,
    appointments.active AS active
FROM
    appointments
WHERE
    appointments.patient_internal_id = %(patient_id)s
        AND appointments.provider_internal_id = %(provider_id)s
        AND appointments.active = 1
"""
PATIENT_SHARED_PROVIDERS = """
SELECT
    patients.internal_id AS patientId,
    patients.external_id AS external_id
FROM
    networks
        INNER JOIN
    patients ON patients.id = networks._patient_id
WHERE
    networks.user_internal_id = %(logged_in_user_id)s
        AND networks._patient_id IN (SELECT
            networks._patient_id
        FROM
            networks
        WHERE
            networks.user_internal_id = %(user_id)s);
"""
GET_PROVIDER = """
SELECT
    providers.id AS dbid,
    providers.internal_id AS id,
    providers.external_id AS external_id,
    providers.degree AS degree,
    providers.`role` AS `role`,
    providers.specialty AS specialty,
    providers.`group` AS `group`,
    GROUP_CONCAT(provider_org.organizations_id) AS org_ids
FROM
    providers
        INNER JOIN
    provider_org ON providers.id = provider_org.providers_id
WHERE
    providers.internal_id = %(provider_id)s
GROUP BY providers.id
"""

CHANNEL_NAME_LIKE = """
SELECT channel_name,
       channel_arn,
       is_patient_enabled
FROM   chime_chats
WHERE  channel_name LIKE concat('%%', %(cname)s, '%%')
"""
