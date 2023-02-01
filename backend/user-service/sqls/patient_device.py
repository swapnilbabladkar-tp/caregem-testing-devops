GET_DEVICE_FROM_DEVICE_READING = """
SELECT DISTINCT imei FROM device_reading where imei like '%{0}'
"""

GET_DEVICE_DETAILS = """
SELECT imei,
       Date_format(start_date, '%%d-%%m-%%Y %%h:%%m:%%s') AS start_date
FROM   device_pairing
WHERE  patient_internal_id = %(id)s
AND    active = 'Y'
"""

GET_PATIENT_DETAILS = """
SELECT activated,
       external_id,
       id,
       internal_id,
       ref_uid,
       remote_monitoring,
       username
FROM   patients
WHERE  internal_id = %(id)s
       AND activated = 1
"""

INSERT_DEVICE_PAIRING = """
INSERT INTO device_pairing
            (patient_internal_id,
             imei,
             start_date,
             active)
VALUES      (%(patient_internal_id)s,
             %(imei)s,
             %(start_date)s,
             %(active)s) 
"""

UPDATE_DEVICE_PAIRING_STATUS = """
UPDATE device_pairing
SET    active = 'N',
       end_date = %(end_date)s
WHERE  id = %(device_pairing_id)s  
"""

GET_DEVICE_PAIRING_STATUS = """
SELECT * from device_pairing
WHERE imei = %(imei)s
AND active = 'Y';
"""
