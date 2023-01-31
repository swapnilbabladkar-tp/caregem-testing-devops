GET_CHANNEL_NAME = """
SELECT channel_name,
       channel_arn,
       is_patient_enabled
FROM   chime_chats
WHERE  channel_name = %(cname_1)s OR channel_name = %(cname_2)s
"""

GET_CHANNEL_NAME_LIKE = """
SELECT channel_name,
       channel_arn,
       latest_message,
       latest_message_timestamp,
       latest_message_sender,
       user_info,
       is_patient_enabled
FROM   chime_chats
WHERE  channel_name LIKE concat('%%', %(cname_1)s, '%%')
"""

INSERT_CHIME_CHATS = """
INSERT INTO chime_chats
            (
                        channel_name,
                        channel_role,
                        channel_arn,
                        chime_bearer_arn,
                        user_info,
                        is_patient_enabled,
                        created_by
            )
            VALUES
            (
                        %(cname)s,
                        %(crole)s,
                        %(c_arn)s,
                        %(bearer_arn)s,
                        %(user_info)s,
                        %(is_patient_enabled)s,
                        %(created_by)s
            )
"""

UPDATE_CHIME_CHATS = """
UPDATE chime_chats
SET    is_patient_enabled = %(is_patient_enabled)s
WHERE  channel_name = %(cname)s
"""

INSERT_CHIME_MEETINGS = """
INSERT INTO call_logs
            (
                        meeting_id,
                        provider_internal_id,
                        patient_internal_id,
                        title,
                        participant_info,
                        scheduled_time,
                        status,
                        type_of_call,
                        org_id
            )
            VALUES
            (
                        %(meeting_id)s,
                        %(owner)s,
                        %(participant)s,
                        %(title)s,
                        %(participant_info)s,
                        %(scheduled_time)s,
                        %(status)s,
                        %(type_of_call)s,
                        %(org_id)s
            )
"""

CHIME_MEETING = """
SELECT *
FROM   call_logs
WHERE  meeting_id = %(meeting_id)s
"""

UPDATE_JOIN_MEETING = """
UPDATE call_logs
SET    start_timestamp = %(start_timestamp)s,
       status = %(status)s,
       participant_info = %(participant_info)s
WHERE  meeting_id = %(meeting_id)s
"""

UPDATE_END_MEETING = """
UPDATE call_logs
SET    end_timestamp=%(end_time)s,
       duration=%(duration)s
WHERE  meeting_id = %(meeting_id)s
"""

ACTIVE_MEETING = """
SELECT 
    meeting_id
FROM
    call_logs
WHERE
    patient_internal_id = %(participant)s
    AND (status = 'NOT STARTED' OR (start_timestamp IS NOT NULL AND end_timestamp IS NULL))
    AND type_of_call = 'video'
    AND scheduled_time BETWEEN (DATE_SUB(UTC_TIMESTAMP(), INTERVAL %(duration)s MINUTE)) AND UTC_TIMESTAMP()
ORDER BY create_time DESC;
"""

UPDATE_ATTENDEE_JOINED = """
UPDATE call_logs 
    SET start_timestamp = %(start_time)s,
        status = %(status)s   
    WHERE meeting_id = %(meeting_id)s and patient_internal_id = %(participant)s
"""

PROVIDER_DETAILS = """
SELECT * FROM providers WHERE external_id IN %(external_ids)s
"""

GET_USER_EXTERNAL_INTERNAL_ID_LIST = """
SELECT external_id, internal_id FROM patients where external_id in %(external_ids)s
UNION
SELECT external_id, internal_id FROM caregivers where external_id in %(external_ids)s
UNION
SELECT external_id, internal_id FROM providers where external_id in %(external_ids)s
"""

UPDATE_LATEST_MESSAGE_DETAILS = """
UPDATE 
  chime_chats 
SET 
  latest_message = %(latest_message)s, 
  latest_message_timestamp = %(latest_message_timestamp)s, 
  latest_message_sender = %(latest_message_sender)s 
WHERE 
  channel_name = %(channel_name)s
"""

GET_CHANNEL_DATA = """SELECT * from chime_chats WHERE channel_name = %(channel_name)s"""
