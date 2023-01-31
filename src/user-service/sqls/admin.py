GET_CUSTOMER_ADMIN_BY_ID = """
SELECT 
    id,
    external_id,
    name,
    _organization_id AS org_id,
    is_read_only
FROM
    customer_admins
WHERE
    id = %(id)s;
"""

DELETE_CUSTOMER_ADMIN = """
DELETE FROM customer_admins 
WHERE
    id = %(id)s;
"""

GET_CUSTOMER_ADMINS = """
SELECT 
    id,
    name,
    external_id
FROM
    customer_admins
WHERE
    _organization_id = %(org_id)s;
"""

UPDATE_CUSTOMER_ADMIN = """
UPDATE 
  customer_admins 
SET 
  is_read_only = %(is_read_only)s, 
  name = %(name)s, 
  update_date = %(update_date)s 
WHERE 
  id = %(id)s
"""

INSERT_CUSTOMER_ADMIN = """
INSERT INTO customer_admins
    (
        external_id,
        internal_id,
        name,
        _organization_id,
        is_read_only,
        create_date
    )
    VALUES
    (
        %(external_id)s,
        %(internal_id)s,
        %(name)s,
        %(org_id)s,
        %(is_read_only)s,
        %(create_date)s
    )
"""
