"""
    This function is to create tasks. What are tasks?

    These are complete projects that are created by Team Leads or product owners

    Sample Task:
        Title: Create a new ride sharing app
        Description: We will use vue.js for front end and lambda for Business logic to create
                    A new ride sharing app, Scope: We will have one backend dev and one front 
                    dev to work on this app. Goals: Every developer is to set goals in a three day
                    threshold. and ensure timely completion of goals. set all goals immediately so
                    we can know the estimated timeframe for this project
        Team members: backend.dev@gmail.com, frontend.dev@gmail.com

    This briefly summarizes the whole ideas of tasks


"""



    # Main Lambda function
import json
import uuid
import boto3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timezone, timedelta
import logging

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
dynamodb = boto3.resource('dynamodb')
cognito = boto3.client('cognito-idp')
table = dynamodb.Table(os.environ['TASKS_TABLE'])

USER_POOL_ID = os.environ['USER_POOL_ID']

def lambda_handler(event, context):
    existing_users = []
    try:
        # Authorization
        claims = event['requestContext']['authorizer']['claims']
        username = claims.get('cognito:username')
        groups = claims.get('cognito:groups', [])
        if isinstance(groups, str):
            groups = [groups]
        if 'admin' not in [g.lower() for g in groups]:
            return error_response(403, 'Only admins can create tasks.')

        # Parse request
        body = json.loads(event['body'])
        assignees = body.get('assignedTo', [])
        assignee_names = body.get('assigneeNames', {})

        if not isinstance(assignees, list) or not assignees:
            return error_response(400, 'assignedTo must be a non-empty list of emails')

        verified_emails = []

        for email in assignees:
            logger.info(f"Processing assignee: {email}")
            user_exists = False
            try:
                # Check if user exists
                cognito.admin_get_user(UserPoolId=USER_POOL_ID, Username=email)
                logger.info(f"User {email} already exists.")
                user_exists = True
                existing_users.append(email)
            except cognito.exceptions.UserNotFoundException:
                logger.info(f"User {email} not found, will create new.")

            # Create or resend user
                try:
                    attributes = [
                        { 'Name': 'email', 'Value': email },
                        { 'Name': 'email_verified', 'Value': 'false' }
                    ]
                    if email in assignee_names:
                        attributes.append({ 'Name': 'name', 'Value': assignee_names[email] })

                    # Create new user or resend invite
                    cognito.admin_create_user(
                        UserPoolId=USER_POOL_ID,
                        Username=email,
                        UserAttributes=attributes,
                        DesiredDeliveryMediums=['EMAIL'],
                    )
                    logger.info(f"User {email} {'re-invited' if user_exists else 'created'}.")

                except Exception as user_err:
                    logger.error(f"Failed to create or invite {email}: {user_err}")
                    return error_response(500, f"Error handling user {email}: {str(user_err)}")
            logger.info(f"appending email {email} to verified emails")
            verified_emails.append(email)
            logger.info(f"verified emails here {verified_emails}")

        # Save task to DynamoDB
        task = {
            'taskId': str(uuid.uuid4()),
            'title': body['title'],
            'description': body['description'],
            'assignedTo': verified_emails,
            'status': 'pending',
            'deadline': body['deadline'],
            'createdBy': username
        }

        logger.info(f"Saving task: {task}")
        table.put_item(Item=task)
        logger.info(f"sending email: {body['title']}, {existing_users}")
        send_email(body['title'], existing_users)
        return {
            'statusCode': 201,
            'headers': cors_headers(),
            'body': json.dumps({ 'message': 'Task created', 'task': task })
        }

    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return error_response(500, str(e))

# Utility: CORS headers
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization,Content-Type",
        "Access-Control-Allow-Methods": "POST,OPTIONS"
    }

# Utility: structured error response
def error_response(status, message):
    return {
        'statusCode': status,
        'headers': cors_headers(),
        'body': json.dumps({ 'error': message })
    }

def send_email(subject, recipients=[]):
    logger.info(f"In the send email function: {subject, recipients}")
    header_msg = subject
    gmail_user = os.environ['GMAIL_USER']
    gmail_password = os.environ['GMAIL_PASSWORD']
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    msg = MIMEMultipart()
    msg['From'] = gmail_user
    msg['To'] = ", ".join(recipients)  # Comma-separated list for header
    msg['Subject'] = f"Invitation to Work on Task: {subject}"
    body = f"Hello, You have been added as a team member to Task: '{header_msg}'. Please login to your portal to set goals"

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, recipients, msg.as_string())
            print(f"Notification sent to {recipients} for task: {subject}")
            return True
    except Exception as e:
        logger.info(f"Failed to send email to {recipients}: {e}")
        return False
