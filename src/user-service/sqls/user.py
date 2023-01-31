INSERT_DELETED_USER = """
INSERT INTO deleted_users
    (
        role,
        _organization_id,
        user_internal_id
    )
    VALUES
    (
                %(role)s,
                %(org_id)s,
                %(user_id)s
    );
"""

DELETE_USER_ORG = """
DELETE
FROM   {org_table}
WHERE  {org_column} = %(id)s
AND    organizations_id = %(org_id)s
"""

NETWORK_USER_BY_USER_ID = """
SELECT 
    *
FROM
    networks
WHERE
    user_internal_id = %(user_id)s;
"""

NETWORK_USER_BY_PATIENT_ID = """
SELECT 
    *
FROM
    networks
WHERE
    _patient_id = %(patient_id)s;
"""

DELETE_NETWORK = """
DELETE FROM networks 
WHERE
    id IN %(ids)s;
"""

GET_ORG_DETAILS = """
SELECT 
    id,
    name
FROM
    organizations
WHERE
    id = %(org_id)s;
"""

GENERATE_INTERNAL_ID = """
INSERT INTO id_sequences (id) VALUES (0);
"""

INSERT_USER_ORG = """
INSERT INTO {org_table} (organizations_id, {org_column}) VALUES(%(org_id)s, %(id)s) 
"""

GET_USER_EXCEPTION = """
SELECT 
    *
FROM
    user_exceptions
WHERE
    ((org_id = %(org_id)s or matching_org_id = %(org_id)s)
        AND status IN ('APPROVED' , 'PENDING', 'DENIED'));
"""

UPDATE_EXCEPTION_STATUS = """
UPDATE 
  user_exceptions
SET 
  status = %(status)s 
WHERE 
  id = %(id)s
"""

GET_EXCEPTION_BY_ID = """
SELECT 
  * 
FROM 
  user_exceptions 
WHERE 
  id = %(id)s
"""

GET_DIAGNOSIS = """
SELECT DISTINCT
    abbreviated_desc, code_detail.code, category
FROM
    code_detail
        LEFT JOIN
    code_category ON code_detail.code = code_category.code
WHERE
    code_detail.code_type = 'ICD10';
"""

UPDATE_PROVIDER_ALERT_STATUS = """
UPDATE 
  providers 
SET 
  alert_receiver = %(alert_status)s 
WHERE 
  id = %(provider_id)s
"""

UPDATE_NETWORK_ALERT_STATUS = """
UPDATE 
  networks 
SET 
  alert_receiver = %(alert_status)s 
WHERE 
  id IN %(network_ids)s
"""
GET_CHANGE_LOG = """
SELECT *
FROM   change_log
WHERE  target_id = %(target_id)s
       AND target_role = %(target_role)s
ORDER  BY utc_timestamp DESC
"""

GET_CUSTOMER_ADMIN_DETAILS = """
SELECT customer_admins.name,
       organizations.name AS org_name
FROM   customer_admins
       JOIN organizations
         ON customer_admins._organization_id = organizations.id
WHERE  customer_admins.id = %(id)s 
"""
