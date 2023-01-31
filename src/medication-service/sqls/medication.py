med_base_query = """
SELECT 
    CAST(medication.id AS CHAR) AS RecordId,
    CAST(medication.patient_internal_id AS CHAR) AS PatientId,
    CAST(medication.product_id AS CHAR) AS ProductId,
    medication.product_short_name AS ProductShortName,
    medication.product_long_name AS ProductLongName,
    medication.quantity AS Quantity,
    medication.unit_strength AS UnitStrength,
    medication.unit_code AS UnitCode,
    medication.sig AS Sig,
    medication.prn AS Prn,
    medication.ingredient AS Ingredient,
    medication.status AS Status,
    medication.created_by AS CreatedBy,
    medication.modified_by AS ModifiedBy,
    DATE_FORMAT(medication.update_time, '%%Y-%%m-%%d %%H:%%i:%%s') AS ModifiedDate,
    DATE_FORMAT(medication.create_time, '%%Y-%%m-%%d %%H:%%i:%%s') AS CreatedDate,
    COALESCE(medication.duration, '') AS Duration,
    COALESCE(medication.info_from, '') AS InfoFrom,
    COALESCE(medication.sig_extra_note, '') AS SigExtraNote,
    medication.medication_reasons AS MedReasons,
    medication.discontinue_reasons as DiscontinuedReason
FROM
    medication
WHERE
    medication.patient_internal_id = %(patient_id)s
        AND medication.status IN %(status)s
"""

UPDATE_MEDICATION = """
UPDATE medication 
SET 
    medication.`status` = %(status)s,
    medication.modified_by = %(modified_by)s,
    medication.update_time = %(upd_date)s,
    medication.discontinue_reasons = %(discontinue_reason)s
WHERE
    medication.id IN %(ids)s;
"""

GET_MEDICATION = """
SELECT 
    id,
    create_time
FROM
    medication
WHERE
    patient_internal_id = %(patient_id)s
        AND product_id = %(product_id)s
        AND status = 'A';
"""

GET_MEDICATION_BY_ID = """
SELECT 
    *
FROM
    medication
WHERE
    id = %(id)s
"""

GET_NETWORK_PROVIDERS = """
SELECT 
    providers.internal_id AS provider_internal_id,
    caregivers.internal_id AS caregiver_internal_id
FROM   
    patients
    JOIN networks
        ON networks._patient_id = patients.id
    LEFT JOIN providers
        ON providers.internal_id = networks.user_internal_id
    LEFT JOIN caregivers
        ON caregivers.internal_id = networks.user_internal_id
WHERE  patients.internal_id = %(patient_internal_id)s """

INSERT_MEDICATION = """
INSERT INTO medication
            (patient_internal_id,
             product_id,
             product_short_name,
             product_long_name,
             quantity,
             unit_strength,
             unit_code,
             sig,
             prn,
             ingredient,
             status,
             created_by,
             modified_by,
             create_time,
             update_time,
             duration,
             info_from,
             sig_extra_note,
             medication_reasons)
VALUES     (%(patient_id)s,
            %(product_id)s,
            %(product_short_name)s,
            %(product_long_name)s,
            %(quantity)s,
            %(unit_strength)s,
            %(unit_code)s,
            %(sig)s,
            %(prn)s,
            %(ingredient)s,
            %(status)s,
            %(created_by)s,
            %(modified_by)s,
            %(crt_date)s,
            %(upd_date)s,
            %(duration)s,
            %(info_from)s,
            %(sig_extra_note)s,
            %(medication_reasons)s); 
"""
