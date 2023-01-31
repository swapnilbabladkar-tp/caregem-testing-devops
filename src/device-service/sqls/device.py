INSERT_DEVICE_READING = """
INSERT INTO device_reading (
  imei, timestamp, battery_voltage, 
  signalStrength, systolic, diastolic, 
  pulse, unit, irregular, raw
) 
VALUES 
  (
    %(imei)s, 
    %(timestamp)s, 
    %(battery_voltage)s, 
    %(signalStrength)s, 
    %(systolic)s, 
    %(diastolic)s, 
    %(pulse)s, 
    %(unit)s, 
    %(irregular)s, 
    %(raw)s
  )
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

UPDATE_DEVICE_PAIRING = """
UPDATE device_pairing
SET    active = 'N',
       end_date = %(end_date)s
WHERE  patient_internal_id = %(patient_internal_id)s  
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
GET_DEVICE_DETAILS = """
SELECT imei,
       Date_format(start_date, '%%d-%%m-%%Y %%h:%%m:%%s') AS start_date
FROM   device_pairing
WHERE  patient_internal_id = %(id)s
AND    active = 'Y'
"""

GET_UNPAIRED_DEVICES = """
SELECT imei,
       Any_value(active) AS active,
       Any_value(Date_format(start_date, '%%Y-%%m-%%d %%h:%%m:%%s')) AS start_date,
       Any_value(Date_format(end_date, '%%Y-%%m-%%d %%h:%%m:%%s')) AS end_date
FROM   device_pairing
WHERE  active = 'N'
       AND SUBSTR(imei, 10, 15) = %(imei)s
GROUP  BY imei
ORDER  BY end_date DESC
"""

GET_PAIRED_USERS = """
SELECT patient_internal_id
FROM   device_pairing
WHERE  active = 'Y'
       AND imei = %(imei)s
"""

GET_NETWORK_PROVIDERS = """
SELECT DISTINCT union_table.external_id AS external_id,
                union_table.internal_id AS internal_id,
                networks.alert_receiver AS user_alert_receiver,
                patients.internal_id as patient_internal_id,
                patients.external_id as patient_external_id
FROM   networks
       JOIN (SELECT internal_id,
                    external_id
             FROM   providers
             UNION
             SELECT internal_id,
                    external_id
             FROM   caregivers) AS union_table
         ON union_table.internal_id = networks.user_internal_id
       JOIN patients
         ON networks._patient_id = patients.id
       JOIN device_pairing
         ON patients.internal_id = device_pairing.patient_internal_id
WHERE  device_pairing.imei = %(imei)s
       AND device_pairing.active = 'Y'
       AND device_pairing.end_date IS NULL; 
"""
