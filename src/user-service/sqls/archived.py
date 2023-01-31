GET_ARCHIVED_USERS = """
SELECT     *
FROM       organizations
INNER JOIN {user_org} AS user_org_1
ON         organizations.id = user_org_1.organizations_id
INNER JOIN {user}
ON         {user}.id = user_org_1.{user}_id
WHERE      organizations.id = %(org_id)s
AND        {user}.activated = 0
"""

GET_USER_BY_INTERNAL_ID = """
SELECT *
FROM   {user}
WHERE  internal_id =%(internal_id)s
"""

GET_DELETED_USER_BY_ORG_ID = """
SELECT deleted_user,
       role,
       user_internal_id
FROM   deleted_users
WHERE  _organization_id = %(org_id)s 
"""
GET_DELETED_USER = """
SELECT id
FROM   deleted_users
WHERE  user_internal_id =%(internal_id)s
       AND _organization_id =%(org_id)s
"""
DELETE_USER_FROM_ARCHIVED = """
DELETE FROM deleted_users
WHERE  id = %(id)s
"""

INSERT_USER_ORG = """
INSERT INTO {org_table}
    (
        organizations_id,
        {org_column_name}
    )
    VALUES
    (
        %(org_id)s,
        %(user_id)s
    )
"""
