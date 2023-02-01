GET_NETWORK_BY_ID = """
SELECT 
    user_internal_id
FROM
    networks
WHERE
    _patient_id = %(patient_id)s;
"""
GET_PROVIDER_DETAILS_BY_INTERNAL_ID = """
SELECT 
    id, internal_id, external_id, role, degree
FROM
    providers
WHERE
    activated = 1 AND internal_id IN %(ids)s;
"""
GET_CAREGIVERS_DETAILS_BY_INTERNAL_ID = """
SELECT 
    id, internal_id, external_id, 'caregiver' AS role
FROM
    caregivers
WHERE
    activated = 1 AND internal_id IN %(ids)s;
"""

GET_ORG_DETAILS = """
SELECT 
    CAST(organizations.id AS CHAR) AS id,
    organizations.name AS name
FROM
    organizations
WHERE
    id IN %(ids)s;
"""

GET_PATIENT_BY_ID = """
SELECT 
    *
FROM
    patients
WHERE
    id = %(id)s;
"""

GET_PROVIDER_BY_ID = """
SELECT 
    *
FROM
    providers
WHERE
    id = %(id)s;
"""

GET_CAREGIVER_BY_ID = """
SELECT 
    *
FROM
    caregivers
WHERE
    id = %(id)s;
"""

GET_PATIENT_EXTERNAL_BY_ID = """
SELECT 
    *
FROM
    patients
WHERE
    external_id = %(external_id)s;
"""

GET_PROVIDER_EXTERNAL_BY_ID = """
SELECT 
    *
FROM
    providers
WHERE
    external_id = %(external_id)s;
"""

GET_CAREGIVER_EXTERNAL_BY_ID = """
SELECT 
    *
FROM
    caregivers
WHERE
    external_id = %(external_id)s;
"""

GET_CUSTOMER_ADMIN_BY_ID = """
SELECT 
    *
FROM
    customer_admins
WHERE
    external_id = %(external_id)s;
"""

INSERT_CHANGE_LOG = """
INSERT INTO change_log
    (`utc_timestamp` ,
     auth_platform,
     auth_ipv4,
     auth_org,
     auth_id,
     auth_role,
     target_id,
     target_role,
     external_id,
     version)
VALUES     
    (
    %(utc_timestamp)s,
    %(auth_platform)s,
    %(auth_ipv4)s,
    %(auth_org)s,
    %(auth_id)s,
    %(auth_role)s,
    %(target_id)s,
    %(target_role)s,
    %(external_id)s,
    %(version)s
    ); 
"""

GET_LINKED_PATIENTS_OF_PROVIDER = """
SELECT patients.internal_id as pat_internal_id
FROM   networks
       INNER JOIN patients
               ON patients.id = networks._patient_id
WHERE  networks.user_internal_id = %(provider_internal_id)s
GROUP  BY patients.id;
"""
