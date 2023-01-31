# RM Values Query

RM_VALES_QUERY = """
SELECT 
    device_pairing.imei,
    device_reading.id,
    patient_internal_id,
    systolic,
    diastolic,
    pulse,
    irregular,
    active,
    timestamp
FROM
    device_reading
        INNER JOIN
    device_pairing ON device_reading.imei = device_pairing.imei
WHERE
    patient_internal_id = %s
        AND timestamp >= start_date
        AND (timestamp <= end_date
        OR end_date IS NULL)
        AND timestamp >= NOW() - INTERVAL %s MONTH
ORDER BY timestamp DESC
"""

# BP HR Query

BP_HR_QUERY = """
SELECT 
    mv.id AS id,
    mv.am_systolic_top,
    mv.am_diastolic_bottom,
    mv.pm_systolic_top,
    mv.pm_diastolic_bottom,
    mv.heart_rate,
    mv.bp_posture,
    mv.submitted_by,
    mv.bp_taken_date,
    mv.bp_taken_date,
    mv.tstamp,
    mv.bp_comments,
    ms.info_text
FROM
    mi_vitals mv
        JOIN
    mi_symptoms ms ON mv.tstamp = ms.enter_date
WHERE
    mv.patient_id = %s
        AND ms.survey_type = 'Vital Signs'
        AND (mv.bp_report = 'yes'
        OR mv.hr_report = 'yes')
        AND tstamp >= NOW() - INTERVAL %s MONTH
ORDER BY tstamp DESC;
"""

# Weight query

WEIGHT_QUERY = """
SELECT 
    mv.weight_kilograms,
    mv.weight_pounds,
    mv.submitted_by,
    mv.weight_taken_date,
    mv.tstamp
FROM
    mi_vitals mv
WHERE
    mv.patient_id = %s
        AND mv.weight_report = 'yes'
        AND tstamp >= NOW() - INTERVAL %s MONTH
ORDER BY tstamp DESC;
"""
