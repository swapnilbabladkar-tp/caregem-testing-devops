PROVIDER_LISTING_QUERY = """
SELECT 
    providers.activated AS activated,
    providers.id AS id,
    providers.username AS username,
    providers.external_id AS external_id,
    providers.internal_id AS internal_id,
    providers.`role` AS role,
    providers.name AS name,
    providers.specialty AS specialty,
    providers.degree AS degree,
    providers.`group` AS grp,
    providers.alert_receiver AS alert_receiver,
    providers.remote_monitoring AS remote_monitoring
FROM
    organizations
        INNER JOIN
    provider_org AS provider_org_1 ON organizations.id = provider_org_1.organizations_id
        INNER JOIN
    providers ON providers.id = provider_org_1.providers_id
WHERE
    organizations.id IN %(org_id)s
        AND (%(role)s is NULL OR providers.`role` = %(role)s)
        AND (%(specialty)s is NULL OR providers.specialty like %(specialty)s)
"""


PROVIDER_DETAILS = """
SELECT 
    activated,
    external_id,
    id,
    providers.`role`,
    name,
    internal_id,
    remote_monitoring,
    providers.`group`,
    specialty,
    degree,
    username
FROM
    providers
WHERE
    providers.id = %(provider_id)s
    AND providers.activated = 1;
"""

PROVIDER_UPDATE_QUERY = """
UPDATE providers 
SET 
    name = %(name)s,
    remote_monitoring = %(remote_monitoring)s,
    providers.`group` = %(group)s,
    specialty = %(specialty)s,
    degree = %(degree)s,
    update_date = %(update_date)s
WHERE
    id = %(id)s;
"""
DELETE_PROVIDER_ORG = """
DELETE FROM provider_org 
WHERE
    providers_id = %(id)s AND organizations_id = %(org_id)s;
"""

DELETE_PROVIDER_NETWORK = """
DELETE FROM networks
WHERE  user_internal_id = %(user_internal_id)s 
"""

ACTIVATE_DEACTIVATE_PROVIDER = """
UPDATE providers 
SET 
    activated = %(value)s
WHERE
    id = %(id)s;
"""

INSERT_PROVIDER = """
INSERT INTO providers
    (
        name,
        external_id,
        internal_id,
        role,
        specialty,
        providers.`group`,
        degree,
        remote_monitoring,
        activated
    )
    VALUES
    (
        %(name)s,
        %(external_id)s,
        %(internal_id)s,
        %(role)s,
        %(specialty)s,
        %(group)s,
        %(degree)s,
        %(remote_monitoring)s,
        %(activated)s
    )
"""

INSERT_PROVIDER_ORG = """
INSERT INTO provider_org
    (
        organizations_id,
        providers_id
    )
    VALUES
    (
        %(org_id)s,
        %(id)s
    )
"""

GET_PROVIDER_DEGREES = """ 
SELECT 
    provider_degree
FROM 
    provider_degrees 
WHERE 
    entity_active = 'Y';"""
