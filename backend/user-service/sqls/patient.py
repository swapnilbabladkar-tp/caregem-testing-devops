PATIENT_DETAILS_QUERY = """
SELECT 
    id,
    activated,
    username,
    external_id,
    internal_id,
    remote_monitoring,
    billing_permission,
    ref_uid
FROM
    patients
WHERE
    id = %(patient_id)s;
"""

PATIENT_DETAILS_BY_REF_UID = """
SELECT 
    external_id, ref_uid, id
FROM
    patients
WHERE
    ref_uid = %(ref_uid)s;
"""

PATIENT_UPDATE_QUERY = """
UPDATE patients 
SET 
    remote_monitoring = %(remote_monitoring)s,
    update_date = %(update_date)s,
    hash_dob=%(hash_dob)s,
    hash_fname=%(hash_fn)s,
    hash_lname=%(hash_ln)s,
    hash_ssn=%(hash_ssn)s
WHERE
    id = %(patient_id)s;
"""

SSN_DOB_FNAME_LNAME_QUERY = """
SELECT 
    external_id AS external_id,
    hash_ssn AS ssn,
    hash_dob AS dob,
    hash_fname AS first_name,
    hash_lname AS last_name
FROM
    patients
WHERE
    hash_ssn =  %(ssn)s OR hash_dob = %(dob)s
        OR hash_fname = %(fname)s
        OR hash_lname = %(lname)s;
"""

PATIENT_DEVICE_QUERY = """
SELECT 
    imei AS device_pairing,
    DATE_FORMAT(start_date, '%%m-%%d-%%Y %%h:%%m:%%s') AS start_date
FROM
    device_pairing
WHERE
    patient_internal_id = %(patient_id)s
        AND active = 'Y'
LIMIT 1;
"""

PATIENT_LISTING_QUERY = """
SELECT 
    patients.activated AS activated,
    patients.id AS id,
    patients.username AS username,
    patients.external_id AS external_id,
    patients.internal_id AS internal_id,
    patients.remote_monitoring AS remote_monitoring,
    COUNT(networks.id) AS network_count
FROM
    organizations
        INNER JOIN
    patient_org AS patient_org_1 ON organizations.id = patient_org_1.organizations_id
        INNER JOIN
    patients ON patients.id = patient_org_1.patients_id
        LEFT OUTER JOIN
    networks ON networks._patient_id = patients.id
WHERE
    organizations.id = %(org_id)s
GROUP BY patients.id
"""

PATIENT_PROVIDER_NETWORK = """
SELECT 
    providers.activated AS activated,
    providers.id AS id,
    providers.external_id AS external_id,
    providers.username AS username,
    providers.name AS name,
    providers.internal_id AS internal_id,
    providers.`role` AS role,
    providers.specialty AS specialty,
    providers.degree AS degree,
    providers.remote_monitoring AS remote_monitoring,
    networks.id AS networks_id,
    networks.alert_receiver AS alert_receiver,
    networks.user_type AS user_type
FROM
    networks
        JOIN
    providers ON networks.user_internal_id = providers.internal_id
        JOIN
    provider_org ON providers.id = provider_org.providers_id
WHERE
    networks._patient_id = %(patient_id)s
        AND provider_org.organizations_id = %(org_id)s;
"""

PATIENT_CAREGIVER_NETWORK = """
SELECT 
    caregivers.activated AS activated,
    caregivers.id AS id,
    caregivers.username AS username,
    caregivers.name AS name,
    caregivers.internal_id AS internal_id,
    caregivers.external_id AS external_id,
    caregivers.remote_monitoring AS remote_monitoring,
    networks.id AS networks_id,
    'caregiver' AS role,
    networks.user_type AS user_type,
    networks.alert_receiver AS alert_receiver
FROM
    networks
        JOIN
    caregivers ON networks.user_internal_id = caregivers.internal_id
        JOIN
    caregiver_org ON caregiver_org.caregivers_id = caregivers.id
WHERE
    networks._patient_id = %(patient_id)s
        AND caregiver_org.organizations_id = %(org_id)s;
"""

DELETE_PATIENT_NETWORK = """
DELETE FROM networks
WHERE  _patient_id = %(patient_id)s 
"""

ACTIVATE_DEACTIVATE_PATIENT = """
UPDATE patients 
SET 
    activated = %(value)s
WHERE
    id = %(id)s;
"""

INSERT_PATIENT = """
INSERT INTO patients
    (
        external_id,
        internal_id,
        ref_uid,
        hash_ssn,
        hash_dob,
        hash_fname,
        hash_lname,
        activated,
        remote_monitoring
    )
    VALUES
    (
        %(external_id)s,
        %(internal_id)s,
        %(ref_uid)s,
        %(hash_ssn)s,
        %(hash_dob)s,
        %(hash_fname)s,
        %(hash_lname)s,
        %(activated)s,
        %(remote_monitoring)s
    )
"""

INSERT_PATIENT_ORG = """
INSERT INTO patient_org
    (
        organizations_id,
        patients_id
    )
    VALUES
    (
        %(org_id)s,
        %(id)s
    )
"""

DELETE_PATIENT_ORG = """
DELETE FROM patient_org 
WHERE
    patients_id = %(id)s AND organizations_id = %(org_id)s;
"""
INSERT_EXCEPTION = """
INSERT INTO user_exceptions
        (
            matching_external_id,
            ref_uid,
            cds_or_s3_file_path,
            matching_fields,
            org_id,
            matching_org_id,
            status,
            comments,
            created_by,
            created_on
        )
        VALUES
        (
            %(matching_external_id)s,
            %(ref_uid)s,
            %(file_path)s,
            %(matching_fields)s,
            %(org_id)s,
            %(matching_org_id)s,
            %(status)s,
            %(comments)s,
            %(created_by)s,
            %(created_on)s
        )
"""
