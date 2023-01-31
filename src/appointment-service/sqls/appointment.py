SAME_NETWORK = """
SELECT *
FROM   networks
WHERE  user_internal_id = %(user_id)s
       AND _patient_id = %(patient_id)s
"""
GET_APPOINTMENT_BY_ID = """
SELECT 
    *
FROM
    appointments
WHERE
    id = %(id)s;
"""
GET_APPOINTMENT_BY_PAT_PRV_ID = """
SELECT 
    id,
    patient_internal_id,
    provider_internal_id,
    date_time,
    active,
    DATE_FORMAT(appointments.created_on,
            '%%a, %%d %%b %%Y %%T') AS created_on,
    DATE_FORMAT(appointments.last_updated_on,
            '%%a, %%d %%b %%Y %%T') AS last_updated_on
FROM
    appointments
WHERE
    patient_internal_id = %(patient_id)s
        AND provider_internal_id = %(provider_id)s
        AND active = 1;
"""
UPDATE_APPOINTMENT = """
UPDATE appointments 
SET 
    active = %(active)s,
    last_updated_on = %(upd_dt)s
WHERE
    id = %(id)s;
"""
INSERT_APPOINTMENT = """
INSERT INTO appointments
            (patient_internal_id,
             provider_internal_id,
             date_time,
             active,
             created_on,
             last_updated_on)
VALUES      (%(patient_id)s,
             %(provider_id)s,
             %(date_time)s,
             %(active)s,
             %(crt_dt)s,
             %(upd_dt)s); 
"""
LIST_APPOINTMENT = """
SELECT 
    appointments.id AS appointment_id,
    appointments.provider_internal_id AS provider_internal_id,
    appointments.patient_internal_id AS patient_internal_id,
    appointments.date_time AS date_time,
    providers.external_id AS external_id,
    providers.degree AS degree,
    providers.specialty As specialty
FROM
    providers
        JOIN
    appointments ON providers.internal_id = appointments.provider_internal_id
WHERE
    appointments.patient_internal_id = %(patient_id)s
        AND appointments.active = 1
ORDER BY appointments.date_time DESC
"""
