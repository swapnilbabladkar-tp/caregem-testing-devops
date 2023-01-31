import logging
import os

import boto3
from botocore.exceptions import ClientError
from custom_exception import GeneralException

ses_client = boto3.client("ses")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class EmailBase:
    """Email base class"""

    def __init__(self):
        """
        Constructor for EmailBase class
        This method will be overwritten by the method defined in the derived class
        """
        # Base class. Extend it or use one of the children
        # using the factory email.get
        pass

    @staticmethod
    def render(self):
        """
        Render method for EmailBase class
        This method will be overwritten by the method defined in the derived class
        """
        return "Base email"

    @staticmethod
    def subject(self):
        """
        Subject method for EmailBase class
        This method will be overwritten by the method defined in the derived class
        """
        return "Base subject"


class WelcomeEmail(EmailBase):
    def __init__(self, org_name, name, url):
        """
        Constructor for WelcomeEmail class
        """
        self.org_name = org_name
        self.name = name
        self.username = "{username}"
        self.url = url
        self.code = "{####}"

    def render(self):
        """
        Render method for WelcomeEmail class
        This method returns the Welcome email content
        """
        return f"""<p>Hi, {self.name}</p>

              <p>You have been invited to join CAREGEM - {self.org_name}</p>

              <p>Login UserName : {self.username} </p>

              <p>Access the following link to change your initial password.</p>

              <p><a href="{self.url}?username={self.username}&code={self.code}">Setup your new password</a></p>

              <p>Best Regards,</p>

              <p>CAREGEM team</p>
            """

    def subject(self):
        """
        Subject method for WelcomeEmail class
        This method returns the subject for the Welcome email
        """
        return f"Welcome to CAREGEM - {self.org_name}"


class PasswordChangeEmail(EmailBase):
    def __init__(self, username, url):
        """
        Constructor for PasswordChangeEmail class
        """
        self.username = username
        self.url = url
        self.code = "{####}"

    def render(self):
        """
        Render method for PasswordChangeEmail class
        This method returns the Password Change email content
        """
        return f"""<p>Hi, {self.username}</p>

            <p>A password change has been requested for your account in CAREGEM</p>

            <p>Access the following link to update your password.</p>
            <p></p>

            <p><a href="{self.url}?username={self.username}&code={self.code}">Setup your new password</a></p>

            <p>If you did not request this change, please contact CAREGEM administrator at
            support@carelogiq.com</p>

            <br/>
            <p>Best Regards</p>

            <p>CAREGEM Staff.</p>
            """

    def subject(self):
        """
        Subject method for PasswordChangeEmail class
        This method returns the subject for the Password Change email
        """
        return "CAREGEM password change request"


class ChangeUserEmail(EmailBase):
    def __init__(self, username, url):
        """
        Constructor for ChangeUserEmail class
        """
        self.username = username
        self.url = url
        self.code = "{####}"
        self.action = "email_change"

    def render(self):
        """
        Render method for ChangeUserEmail class
        This method returns the User Email Change email content
        """
        return f"""
            <p>Hi, {self.username}</p>

            <p>An email change has been requested for your account in CAREGEM,
            and it requires you to confirm your email.</p>

            <p>Access the following link to confirm your email using your current password.</p>

            <p><a href="{self.url}?username={self.username}&code={self.code}&action={self.action}">Confirm your new email</a></p>

            <p>If you did not request this change, please contact CAREGEM administrator at
            support@carelogiq.com</p>

            <br/>
            <p>Best Regards</p>

            <p>CAREGEM Staff.</p>
        """

    def subject(self):
        """
        Subject method for ChangeUserEmail class
        This method returns the subject for the User Email Change email
        """
        return "CAREGEM account email change request"


class UserLockedEmail(EmailBase):
    def __init__(self, first_name, attempts_count):
        """
        Constructor for UserLockedEmail class
        """
        self.first_name = first_name
        self.attempts_count = attempts_count

    def render(self):
        """
        Render method for UserLockedEmail class
        This method returns the User Locked email content
        """
        return f"""
            <p>Hi, {self.first_name}</p>

            <p>Due to security reasons, your account in CAREGEM has been locked after {self.attempts_count} failed login attempts.</p>

            <p>Please contact CAREGEM administrator at support@carelogiq.com to request for unlock.</p>

            <br/>
            <p>Best Regards,</p>

            <p>CAREGEM team</p>
        """

    def subject(self):
        """
        Subject method for UserLockedEmail class
        This method returns the subject for the User Locked email
        """
        return "CAREGEM account locked"


class NewAdminEmail(EmailBase):
    def __init__(self, org_name, username, user_email):
        """
        Constructor for NewAdminEmail class
        """
        self.org_name = org_name
        self.username = username
        self.user_email = user_email

    def render(self):
        """
        Render method for NewAdminEmail class
        This method returns the New Admin email content
        """
        return f"""
            <p>Hi,</p>

            <p>A new Customer admin has been included in your organization.</p>

            <p>
                User name: <span class="user-info">{self.username} </span><br/>
                Email: <span class="user-info">{self.user_email} </span><br/>
                Organization: <span class="user-info">{self.org_name}</span><br/>
            </p>
            <br/>
            <p>Best Regards,</p>

            <p>CAREGEM team</p>
        """

    def subject(self):
        """
        Subject method for NewAdminEmail class
        This method returns the subject for the New Admin email
        """
        return f"New Customer administrator on {self.org_name}"


class RemovedAdminEmail(EmailBase):
    def __init__(self, org_name, user_name, user_email):
        """
        Constructor for RemovedAdminEmail class
        """
        self.org_name = org_name
        self.user_name = user_name
        self.user_email = user_email

    def render(self):
        """
        Render method for RemovedAdminEmail class
        This method returns the Removed Admin email content
        """
        return f"""
            <p>Hi,</p>

            <p>The following Customer administrator has been removed from your organization.</p>

            <p>
                User name: <span class="user-info">{self.user_name}</span><br/>
                Email: <span class="user-info">{self.user_email}</span><br/>
                Organization: <span class="user-info">{self.org_name}</span><br/>
            </p>


            <br/>
            <p>Best Regards,</p>

            <p>CAREGEM team</p>
        """

    def subject(self):
        """
        Subject method for RemovedAdminEmail class
        This method returns the subject for the Removed Admin email
        """
        return "Removed Customer admin from CAREGEM - %s" % self.org_name


class UpdatePatientEmail(EmailBase):
    def __init__(self, org_name, name):
        """
        Constructor for UpdatePatientEmail class
        """
        self.org_name = org_name
        self.name = name

    def render(self):
        """
        Render method for UpdatePatientEmail class
        This method returns the Patient Update email content
        """
        return f"""
            <p>Hi,</p>

            <p>Patient {self.name} is updated. Please login to system an check the details</p>

            <br/>
            <p>Best Regards,</p>

            <p>CAREGEM team</p>
        """

    def subject(self):
        """
        Subject method for UpdatePatientEmail class
        This method returns the subject for the Patient Update email
        """
        return f"Patient Update on {self.org_name}"


class CDSUpdateEmail(EmailBase):
    def __init__(self, content, sub):
        """
        Constructor for CDSUpdateEmail class
        """
        self.content = content
        self.sub = sub

    def render(self):
        """
        Render method for CDSUpdateEmail class
        This method returns the CDS Update email content
        """
        return f"""<p>{self.content}</p>"""

    def subject(self):
        """
        Subject method for CDSUpdateEmail class
        This method returns the subject for the CDS Update email
        """
        return f"""{self.sub}"""


class SurveyCompletionEmail(EmailBase):
    def __init__(self, name):
        """
        Constructor for SurveyCompletionEmail class
        """
        self.name = name

    def render(self):
        """
        Render method for SurveyCompletionEmail class
        This method returns the Survey Completion email content
        """
        return f"""
            <p>Hi, {self.name}</p>

            <p>Thank you for completing a health survey in CAREGEM. This information may help to keep track of overall changes in your health.</p>

            <p>Please do call your doctor as you would usually for advise regarding medical problems you may be experiencing. As this survey may not be reviewed immediately, please do NOT rely upon this survey to receive medical attention.</p>

            <p style="text-align:center;">IF YOU THINK THIS IS A MEDICAL EMERGENCY, OR YOUR SYMPTOMS ARE WORRISOME PLEASE CALL 911 OR GO TO THE NEAREST EMERGENCY ROOM.</p>

        """

    def subject(self):
        """
        Subject method for SurveyCompletionEmail class
        This method returns the subject for the Survey Completion email
        """
        return "Thank you for completing a health survey in CAREGEM"


def send_mail_to_user(destination, content) -> None:
    """
    This function uses AWS SES to send email to the
    destination and content class instance provided as input
    """
    try:
        source = os.getenv("EMAIL_SOURCE")
        source_arn = os.getenv("EMAIL_SOURCE_ARN")
        logger.info("Email Source is %s", source)
        response = ses_client.send_email(
            Destination={
                "ToAddresses": destination,
            },
            Message={
                "Body": {
                    "Html": {
                        "Charset": "UTF-8",
                        "Data": content.render(),
                    },
                    "Text": {
                        "Charset": "UTF-8",
                        "Data": "This is the message body in text format.",
                    },
                },
                "Subject": {
                    "Charset": "UTF-8",
                    "Data": content.subject(),
                },
            },
            Source=source,
            SourceArn=source_arn,
        )
        print(response)
    except ClientError as err:
        logger.error(err)
    except GeneralException as exp:
        logger.error(exp)
