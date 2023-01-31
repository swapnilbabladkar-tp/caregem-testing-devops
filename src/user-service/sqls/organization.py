GET_ORG_LISTING = """
SELECT 
    organizations.id AS id, organizations.NAME AS name
FROM
    organizations;
"""
INSERT_ORG = """
INSERT INTO organizations
            (name,
             email,
             phone_1,
             phone_2,
             address,
             city,
             state,
             zipcode,
             phone_1_country_code,
             phone_2_country_code)
VALUES      ( %(name)s,
              %(email)s,
              %(phone_1)s,
              %(phone_2)s,
              %(address)s,
              %(city)s,
              %(state)s,
              %(zipcode)s,
              %(phone_1_country_code)s,
              %(phone_2_country_code)s); 
"""
UPDATE_ORG = """
UPDATE organizations
SET    name=%(name)s,
       email=%(email)s,
       phone_1=%(phone_1)s,
       phone_2=%(phone_2)s,
       address=%(address)s,
       city=%(city)s,
       state=%(state)s,
       zipcode=%(zipcode)s,
       phone_1_country_code=%(phone_1_country_code)s,
       phone_2_country_code=%(phone_2_country_code)s
WHERE  id=%(id)s
"""

GET_ORG = """
SELECT 
    *
FROM
    organizations
WHERE
    id = %(id)s;
"""
