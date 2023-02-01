PATIENT_DIAGNOSIS_QUERY = """
SELECT DISTINCT
    abbreviated_desc, assigned_code
FROM
    code_detail cd
        JOIN
    code_category cc ON cd.code = cc.code
        JOIN
    code_assigned ca ON cd.code = ca.assigned_code
WHERE
    ca.patient_internal_id = %(patient_id)s;
"""

SAVE_DIAGNOSIS_QUERY = """
INSERT INTO code_assigned
            (assigned_code,
             patient_internal_id)
VALUES      (%(code)s,
             %(patient_id)s) 
"""

DELETE_DIAGNOSIS_QUERY = """
DELETE FROM code_assigned 
WHERE
    patient_internal_id = %(patient_id)s
    AND assigned_code IN %(codes)s
"""
