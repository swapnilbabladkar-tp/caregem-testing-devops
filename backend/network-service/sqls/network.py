PATIENT_PROVIDER_NETWORK = """
SELECT
    networks.id AS networks_id,
    providers.activated,
    providers.id,
    providers.external_id,
    providers.username,
    providers.name,
    providers.internal_id,
    providers .`role`,
    providers.specialty,
    providers.degree,
    providers.remote_monitoring,
    networks.alert_receiver,
    networks.user_type
FROM
    networks
        JOIN
    providers ON networks.user_internal_id = providers.internal_id
        JOIN
    provider_org ON providers.id = provider_org.providers_id
WHERE
    networks._patient_id = %(patient_id)s
        AND provider_org.organizations_id = %(org_id)s
"""
PATIENT_CAREGIVER_NETWORK = """
SELECT
    networks.id AS networks_id,
    caregivers.activated,
    caregivers.id,
    caregivers.username,
    caregivers.name,
    caregivers.internal_id,
    caregivers.external_id,
    caregivers.remote_monitoring,
    'caregiver' As role,
    networks.user_type,
    networks.alert_receiver
FROM
    networks
        JOIN
    caregivers ON networks.user_internal_id = caregivers.internal_id
        JOIN
    caregiver_org ON caregivers.id = caregiver_org.caregivers_id
WHERE
    networks._patient_id = %(patient_id)s
        AND caregiver_org.organizations_id = %(org_id)s
"""
GET_CONNECTED_PATIENT_OF_USER = """
SELECT
    patients.id,
    patients.external_id,
    patients.internal_id,
    patients.remote_monitoring
FROM
    patients
        INNER JOIN
    networks ON patients.id = networks._patient_id
WHERE
    networks.user_internal_id = %(user_id)s;
"""
GET_ORG_DETAILS_BY_PATIENT_ID = """
SELECT  organizations.id,
        organizations.name
FROM   patient_org
JOIN   organizations
ON     organizations.id = patient_org.organizations_id
WHERE  patients_id = %(patient_id)s
"""
GET_ALL_PATIENT_NETWORK = """
SELECT
    networks.id AS networks_id
FROM
    networks
        JOIN
    providers ON networks.user_internal_id = providers.internal_id
        JOIN
    provider_org ON providers.id = provider_org.providers_id
WHERE
    networks._patient_id = %(patient_id)s
        AND provider_org.organizations_id = %(org_id)s
UNION SELECT
    networks.id AS networks_id
FROM
    networks
        JOIN
    caregivers ON networks.user_internal_id = caregivers.internal_id
        JOIN
    caregiver_org ON caregivers.id = caregiver_org.caregivers_id
WHERE
    networks._patient_id = %(patient_id)s
        AND caregiver_org.organizations_id = %(org_id)s
"""
DELETE_NETWORK_BY_ID = """
DELETE FROM networks
WHERE
    id IN %(ids)s;
"""
GET_USER_COUNT_OF_ORG = """
SELECT Count(*) as count
FROM   {user_type}
JOIN   {org_table}
ON     {user_type}.id = {org_table}.{org_column}
WHERE  {org_table}.organizations_id = %(org_id)s
AND    {user_type}.internal_id IN %(ids)s
"""
INSERT_USER_TO_NETWORK = """
INSERT INTO networks
            (user_type,
             _patient_id,
             alert_receiver,
             user_internal_id)
VALUES      (%(user_type)s,
             %(patient_id)s,
             %(alert_receiver)s,
             %(user_id)s)
"""
GET_EXISTING_USER_NETWORK = """
SELECT
    user_internal_id,
    _patient_id
FROM
    networks
WHERE
    _patient_id = %(patient_id)s
        AND user_internal_id IN %(user_ids)s;
"""
GET_EXISTING_USER_NETWORK_FOR_CAREGIVER = """
SELECT
    user_internal_id,
    _patient_id
FROM
    networks
WHERE
    _patient_id IN %(patient_ids)s
        AND user_internal_id = %(user_id)s;
"""

GET_CAREGIVER_NETWORK = """
SELECT
    networks.id AS networks_id
FROM
    networks
        JOIN
    caregivers ON networks.user_internal_id = caregivers.internal_id
        JOIN
    caregiver_org ON caregiver_org.caregivers_id = caregivers.id
WHERE
    networks.user_internal_id = %(user_id)s
        AND caregiver_org.organizations_id = %(org_id)s
"""


INSERT_USER_TO_PATIENT_NETWORK = """
INSERT INTO networks
            (connected_user,
            user_type,
            _patient_id,
            alert_receiver,
            user_internal_id)
VALUES (%s, %s, %s, %s, %s)
"""

DELETE_USER_NETWORKS = """
DELETE FROM networks
WHERE id IN ({f_str})
"""
