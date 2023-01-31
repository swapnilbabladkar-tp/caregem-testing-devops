import json
import logging
from datetime import datetime

import pymysql
from shared import get_db_connect
from sqls.chime import UPDATE_ATTENDEE_JOINED

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


connection = get_db_connect()


def update_attendee_joined(cnx, meeting_id, participant, start_time):
    """
    Get the Patient Lab data
    """
    try:
        params = {
            "meeting_id": meeting_id,
            "status": "DRAFT",
            "participant": participant,
            "start_time": start_time,
        }
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_ATTENDEE_JOINED, params)
            cnx.commit()
            return f"{participant} joined Meeting"
    except pymysql.MySQLError as err:
        logger.exception(err)
        return 500, str(err)


def lambda_handler(event, context):
    """
    Handler function
    """
    participant = event["detail"]["externalUserId"]
    meeting_id = event["detail"]["meetingId"]
    start_time = datetime.fromisoformat(event["time"] + "+00:00")
    user_result = update_attendee_joined(
        connection, meeting_id, participant, start_time
    )
    return {"statusCode": 200, "body": json.dumps(user_result)}
