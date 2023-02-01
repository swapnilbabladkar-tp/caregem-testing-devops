from http import HTTPStatus
import json
import logging
import os
import uuid
from datetime import datetime

import boto3
import pymysql
from botocore.exceptions import ClientError
from shared import (
    check_user_access_for_patient_data,
    find_user_by_external_id,
    find_user_by_internal_id,
    get_db_connect,
    get_headers,
    get_phi_data,
    get_user_org_ids,
    read_as_dict,
    get_s3_config,
)
from sms_util import (
    get_join_video_call_sms_content,
    publish_text_message,
    get_phone_number_from_phi_data,
)
from sqls.chime import (
    ACTIVE_MEETING,
    CHIME_MEETING,
    INSERT_CHIME_MEETINGS,
    UPDATE_END_MEETING,
    UPDATE_JOIN_MEETING,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

connection = get_db_connect()

aws_region = os.getenv("AWSREGION")
user_pool_id = os.getenv("USER_POOL_ID")
chime_instance_arn = os.getenv("CHIME_INSTANCE_ARN")
aws_chime_pstn_number = os.getenv("AWS_CHIME_PSTN_NUMBER")
environment = os.getenv("ENVIRONMENT")
bucket_name = os.getenv("BUCKET_NAME")
file_name = os.getenv("S3_FILE_NAME")


cognito_client = boto3.client("cognito-idp", region_name=aws_region)
chime_client = boto3.client("chime", region_name=aws_region)
dynamodb = boto3.resource("dynamodb", region_name=aws_region)
s3_client = boto3.client("s3", region_name=aws_region)


def get_common_org_id(cnx, patient_id, provider_id):
    """
    Get the common org id.
    :params patient_id, provider_id, cnx obj
    :Return common org_ids
    """
    pat_orgs = get_user_org_ids(cnx, "patient", internal_id=patient_id)
    prv_orgs = get_user_org_ids(cnx, "providers", internal_id=provider_id)
    common_org = set(pat_orgs).intersection(set(prv_orgs))
    if common_org:
        return list(common_org)
    return None


def get_meeting(meeting_id):
    """
    Returns Meeting Details from Chime for meeting_id given as input
    Returns empty list if not found
    """
    try:
        response = chime_client.get_meeting(MeetingId=meeting_id)
        return response["Meeting"]
    except chime_client.exceptions.NotFoundException as err:
        logger.error(err)
        return []
    except ClientError as err:
        logger.error(err)
        return []


def get_attendee(meeting_id, attendee_id):
    """
    Returns Attendee details from Chime given meeting and attendee id as input
    Returns None if not found
    Returns empty list on encountering ClientError
    """
    try:
        response = chime_client.get_attendee(
            MeetingId=meeting_id, AttendeeId=attendee_id
        )
        return response["Attendee"]
    except chime_client.exceptions.NotFoundException as err:
        logger.error(err)
        return None
    except ClientError as err:
        logger.error(err)
        return []


def delete_meeting(meeting_id):
    """
    Deletes meeting with given meeting_id from Chime
    """
    try:
        response = chime_client.delete_meeting(MeetingId=meeting_id)
        return response
    except ClientError as err:
        logger.error(err)


def create_attendee(meeting_id, user_id):
    """
    Creates attendee for a given meeting ID
    Returns Attendee details in response
    """
    try:
        response = chime_client.create_attendee(
            MeetingId=meeting_id, ExternalUserId=str(user_id)
        )
        return response["Attendee"]
    except ClientError as err:
        logger.error(err)


def create_meeting(owner):
    """
    Creates meeting for user given internal id as input
    Returns Meeting data in response
    """
    external_meeting_id = str(owner) + "_" + str(uuid.uuid4())
    try:
        response = chime_client.create_meeting(
            ClientRequestToken=str(uuid.uuid4()),
            ExternalMeetingId=external_meeting_id[0:64],
            MeetingHostId=str(owner),
        )
        return response["Meeting"]
    except ClientError as err:
        logger.error(err)


def create_meeting_dial_out(meeting_id, to_phone_number, join_token):
    """
    Initiates PSTN call to given phone number from the given meeting id and
    adds it to the meeting using the join_token for attendee provided as input
    """
    try:
        chime_client.create_meeting_dial_out(
            MeetingId=meeting_id,
            FromPhoneNumber=aws_chime_pstn_number,
            ToPhoneNumber=to_phone_number,
            JoinToken=join_token,
        )
        return True
    except ClientError as err:
        logger.error(err)
        return False


def save_meeting_details(cnx, data):
    """
    Inserts Meeting details in call_logs table
    """
    params = {
        "meeting_id": data["meeting_id"],
        "owner": data["owner"],
        "participant": data["participant"],
        "title": data["title"],
        "type_of_call": data["type_of_call"],
        "org_id": data["org_id"],
        "participant_info": json.dumps(data["attendees"]),
        "scheduled_time": data["scheduled_time"],
        "status": data["status"],
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(INSERT_CHIME_MEETINGS, params)
            cnx.commit()
            logger.info("Successfully created Meeting")
            return True
    except pymysql.MySQLError as err:
        logger.error(err)
        return None


def get_meeting_details(cnx, meeting_id):
    """
    Retrieves meeting details from call_logs based on meeting_id
    """
    params = {"meeting_id": meeting_id}
    result = read_as_dict(cnx, CHIME_MEETING, params)
    if result:
        return result[0]
    return None


def send_sms(cnx, participant_list, meeting_data):
    """
    Sends SMS to patient to join the meeting initiated by a provider
    """
    for participant in participant_list:
        patient = find_user_by_internal_id(cnx, participant, "patient")
        phi_data = get_phi_data(patient["external_id"], dynamodb)
        s3_config = get_s3_config(bucket_name, file_name, s3_client)
        message_content = get_join_video_call_sms_content(
            s3_config.get(environment, {}).get("WebApp", "")
        )
        if phi_data:
            phone_number = get_phone_number_from_phi_data(phi_data)
            try:
                message_id = publish_text_message(phone_number, message_content)
                logger.info(
                    "Message sent for %s, message id %s", participant, message_id
                )
            except Exception:
                logger.info("Failed to send message")
        else:
            logger.info("Patient doesn't have cell number")


def update_join_meeting(cnx, meeting_data, attendee):
    """
    Updates call_log details with patient data when the patient joins a meeting
    """
    participant_info = json.loads(meeting_data["participant_info"])
    participant_info.update({attendee["ExternalUserId"]: attendee["AttendeeId"]})
    params = {
        "start_timestamp": datetime.utcnow(),
        "status": "DRAFT",
        "participant_info": json.dumps(participant_info),
        "meeting_id": meeting_data["meeting_id"],
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_JOIN_MEETING, params)
            cnx.commit()
        return True
    except pymysql.MySQLError as err:
        logger.error(err)
        return None


def update_end_meeting_status(cnx, meeting_id):
    """
    Updates Call log with end_time and duration of the meeting
    when the meeting is ended
    """
    meeting = get_meeting_details(cnx, meeting_id)
    end_time = datetime.utcnow()
    if isinstance(meeting["start_timestamp"], datetime):
        duration = (end_time - meeting["start_timestamp"]).total_seconds()
    else:
        duration = 0
    params = {
        "end_time": end_time,
        "duration": int(duration),
        "meeting_id": meeting_id,
    }
    try:
        with cnx.cursor() as cursor:
            cursor.execute(UPDATE_END_MEETING, params)
            cnx.commit()
        return True
    except pymysql.MySQLError as err:
        logger.error(err)
        return None


def create_meeting_with_attendee(cnx, owner, participant_list, pstn=None):
    """
    This Function:
    1. Creates Meeting and Attendee Data in Chime
    2. Notifies patient to join the created meeting via SMS
    3. Saves meeting details in Call Logs
    4. Returns Meeting Details in response
    """
    meeting_response = {}
    participant_data = {}
    meeting_data = create_meeting(owner)
    attendees_data = create_attendee(meeting_data["MeetingId"], owner)
    data = dict()
    participant = ",".join(participant_list)
    org_ids = get_common_org_id(cnx, participant, owner)
    data["meeting_id"] = meeting_data["MeetingId"]
    data["org_id"] = org_ids[0] if org_ids else 0
    data["participant"] = participant
    data["title"] = meeting_data["ExternalMeetingId"]
    data["scheduled_time"] = datetime.utcnow()
    data["status"] = "NOT STARTED"
    data["owner"] = owner
    data["type_of_call"] = "phone" if pstn else "video"
    data["attendees"] = {attendees_data["ExternalUserId"]: attendees_data["AttendeeId"]}
    data["attendees"].update({item: "" for item in participant_list})
    if pstn:
        participant_data = create_attendee(meeting_data["MeetingId"], participant)
        data["attendees"][participant] = participant_data["AttendeeId"]
    if save_meeting_details(cnx, data):
        if not pstn:
            send_sms(cnx, participant_list, meeting_data)
            meeting_response["Meeting"] = meeting_data
            meeting_response["Attendee"] = attendees_data
            meeting_response["title"] = meeting_data["ExternalMeetingId"]
            return 200, meeting_response
        if participant_data:
            response = create_meeting_dial_out(
                meeting_data["MeetingId"],
                pstn["to_phone_number"],
                participant_data["JoinToken"],
            )
            if response:
                meeting_response["Meeting"] = meeting_data
                meeting_response["Attendee"] = attendees_data
                meeting_response["title"] = meeting_data["ExternalMeetingId"]
                return 200, meeting_response
        return 500, "Error while pstn calling"
    return 500, "Error while creating meeting"


def join_meeting(cnx, meeting_id, participant):
    """
    This Function:
    1. Gets meeting details
    2. Adds participant to meeting based if meeting is present
       and participant is allowed to join the meeting
    3. Returns Meeting Details in response
    """
    meeting_response = dict()
    meeting_response["Meeting"] = get_meeting(meeting_id)
    if not meeting_response["Meeting"]:
        return 400, "Meeting Has Ended"
    meeting_data = get_meeting_details(cnx, meeting_id)
    if meeting_data:
        participants = json.loads(meeting_data["participant_info"])
        if str(participant) not in participants:
            return 400, "Participant Not allowed"
        attendee_response = create_attendee(meeting_id, participant)
        response = update_join_meeting(cnx, meeting_data, attendee_response)
        if response:
            meeting_response["Attendee"] = attendee_response
            return 200, meeting_response
        return 500, "Error while joining Meeting"
    return 400, "Meeting not found"


def end_meeting(cnx, meeting_id):
    """
    Deletes meeting from chime
    """
    response = update_end_meeting_status(cnx, meeting_id)
    if response:
        delete_meeting(meeting_id)
        return 200, "Successfully Ended the meeting"
    return 500, "Error while ending the meeting"


def get_active_meeting(cnx, participant, duration=5):
    """
    This Function:
    1. Gets Active Meeting ID from call_log for meetings started
       during last "n"(default=5) minutes
    2. Gets meeting details for the meeting id from chime
    3. Gets user data for participant
    4. Returns Meeting details and participant info in response
    """
    result = read_as_dict(
        cnx, ACTIVE_MEETING, {"participant": participant, "duration": duration}
    )
    if result:
        meeting = get_meeting(result[0]["meeting_id"])
        if meeting:
            owner = meeting["ExternalMeetingId"].split("_")[0]
            user = find_user_by_internal_id(cnx, owner, "providers")
            user_profile = get_phi_data(user["external_id"], dynamodb)
            meeting["user_info"] = user_profile
            return 200, meeting
    return 200, "No active Meeting"


def lambda_handler(event, context):
    """
    Handler function for chime
    """
    # auth_user = get_logged_in_user(cognito_user["sub"], None)
    auth_user = event["requestContext"].get("authorizer")
    external_id = auth_user["userSub"]
    role = auth_user["userRole"]
    user_data = find_user_by_external_id(connection, external_id, role)
    path = event["path"].split("/")
    query_string = event["queryStringParameters"]
    status_code = HTTPStatus.NOT_FOUND
    result = {}
    if "createMeeting" in path:
        owner = event["pathParameters"].get("owner")
        form_data = json.loads(event["body"])
        pstn = {}
        if form_data.get("cell"):
            pstn["to_phone_number"] = form_data["cell"]
        status_code, result = create_meeting_with_attendee(
            connection, owner, form_data["participant_list"], pstn
        )
    elif "joinMeeting" in path:
        meeting_id = event["pathParameters"].get("meetingId")
        participant = event["pathParameters"].get("participant")
        status_code, result = join_meeting(connection, meeting_id, participant)
    elif "activeMeeting" in path:
        participant = event["pathParameters"].get("participant")
        is_allowed, access_result = check_user_access_for_patient_data(
            cnx=connection,
            role=role,
            user_data=user_data,
            patient_internal_id=participant,
        )
        if is_allowed and access_result and access_result["message"] == "Success":
            if query_string:
                duration = event["queryStringParameters"].get("duration")
                status_code, result = get_active_meeting(
                    connection, participant, duration
                )
            else:
                status_code, result = get_active_meeting(connection, participant)
        else:
            status_code = HTTPStatus.BAD_REQUEST
            result = access_result
    elif "endMeeting" in path:
        meeting_id = event["pathParameters"].get("meetingId")
        status_code, result = end_meeting(connection, meeting_id)
    return {
        "statusCode": status_code,
        "body": json.dumps(result),
        "headers": get_headers(),
    }
