GET_CAREGIVER_LISTING = """
SELECT 
    caregivers.activated,
    caregivers.id,
    caregivers.external_id AS external_id,
    caregivers.internal_id AS internal_id,
    caregivers.remote_monitoring
FROM
    organizations
        INNER JOIN
    caregiver_org AS caregiver_org_1 ON organizations.id = caregiver_org_1.organizations_id
        INNER JOIN
    caregivers ON caregivers.id = caregiver_org_1.caregivers_id
WHERE
    organizations.id = %(org_id)s;
"""

GET_CAREGIVER_DETAILS = """
SELECT 
    activated,
    external_id,
    id,
    name,
    internal_id,
    remote_monitoring,
    username
FROM
    caregivers
WHERE
    caregivers.id = %(caregiver_id)s;
"""

INSERT_CAREGIVER = """
INSERT INTO caregivers
    (
        external_id,
        internal_id,
        name,
        activated,
        create_date
    )
    VALUES
    (
        %(external_id)s,
        %(internal_id)s,
        %(name)s,
        %(activated)s,
        %(create_date)s
    )
"""

INSERT_CAREGIVER_ORG = """
INSERT INTO caregiver_org
    (
        organizations_id,
        caregivers_id
    )
    VALUES
    (
        %(org_id)s,
        %(id)s
    )
"""

DELETE_CAREGIVER_ORG = """
DELETE FROM caregiver_org 
WHERE
    caregivers_id = %(id)s AND organizations_id = %(org_id)s;
"""

UPDATE_CAREGIVER_QUERY = """
UPDATE caregivers 
SET 
    update_date = %(update_date)s,
    name=%(name)s
WHERE
    id = %(caregiver_id)s;
"""

DELETE_CAREGIVER_NETWORK = """
DELETE FROM networks
WHERE  user_internal_id = %(user_internal_id)s 
"""

ACTIVATE_DEACTIVATE_CAREGIVER = """
UPDATE caregivers 
SET 
    activated = %(value)s
WHERE
    id = %(id)s;
"""
