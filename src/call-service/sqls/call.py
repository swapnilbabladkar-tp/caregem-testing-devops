CALL_NOTES = """
SELECT id,
       note_detail
FROM   notes
WHERE  note_type = 'call_notes' 
"""
CALL_BASE_QUERY = """
SELECT DISTINCT Concat(providers.name, ', ', providers.degree) AS provider_name,
                call_logs.provider_internal_id,
                call_logs.patient_internal_id,
                call_logs.id,
                call_logs.duration,
                call_logs.start_timestamp,
                call_logs.type_of_call,
                call_logs.notes,
                call_logs.status,
                call_logs.start_timestamp
FROM            call_logs
JOIN            providers
ON              call_logs.provider_internal_id = providers.internal_id
WHERE           call_logs.patient_internal_id = %(patient_id)s
AND             providers.remote_monitoring = "Y"
AND             (%(n_org_id)s IS NULL OR  call_logs.org_id = %(org_ids)s)
AND             call_logs.status IN %(status)s
ORDER BY        call_logs.start_timestamp DESC
"""

REMOTE_MONITORING_PROVIDER = """
SELECT remote_monitoring
FROM   providers
WHERE  internal_id = %(provider_id)s
       AND remote_monitoring = 'Y' 
"""

INSERT_CALL_RECORDS = """
INSERT INTO call_logs
            (patient_internal_id,
             provider_internal_id,
             start_timestamp,
             duration,
             type_of_call,
             org_id,
             status,
             notes)
VALUES      (%(patient_internal_id)s,
             %(provider_internal_id)s,
             %(start_timestamp)s,
             %(duration)s,
             %(type_of_call)s,
             %(org_id)s,
             %(status)s,
             %(notes)s) 
"""

UPDATE_CALL_RECORDS = """
UPDATE call_logs
SET    status = %(status)s,
       notes = %(notes)s
WHERE  call_logs.id = %(id)s
"""

UPDATE_MANUAL_CALL_RECORDS = """
UPDATE call_logs
SET    status = %(status)s,
       notes = %(notes)s,
       start_timestamp = %(start_timestamp)s,
       duration = %(duration)s
WHERE  call_logs.id = %(id)s
"""

CALL_LOGS_MONTHLY_TOTAL_RM_PRV = """
SELECT SUM(duration) AS total
FROM   call_logs calls
       left join providers prv
              ON calls.provider_internal_id = prv.internal_id
WHERE  org_id = %(org_id)s
       AND patient_internal_id = %(patient_id)s
       AND prv.remote_monitoring = 'Y'
       AND Month(start_timestamp) = %(month)s
       AND Year(start_timestamp) = %(year)s
       AND status IN %(status)s
"""

CALL_LOGS_MONTHLY_TOTAL = """
SELECT SUM(duration) AS total
FROM   call_logs calls
WHERE  patient_internal_id = %(patient_id)s
       AND Month(start_timestamp) = %(month)s
       AND Year(start_timestamp) = %(year)s
       AND status IN %(status)s
"""

DRAFT_CALL_RECORD_BELONGS_TO_PROVIDER = """
SELECT  id
FROM    call_logs
WHERE   id = %(call_id)s
    AND provider_internal_id = %(provider_internal_id)s
    AND status = "DRAFT"
"""

SOFT_DELETE_DRAFT_CALL_RECORD = """
UPDATE call_logs
SET    status = "DELETED"
WHERE  id = %(call_id)s
"""
