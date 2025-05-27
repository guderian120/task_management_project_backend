# Importing necessary libraries for AWS integration, JSON handling, email sending, and logging
import json
import boto3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timezone, timedelta
import logging

# Configure logging for CloudWatch analysis
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Set logging level to DEBUG for detailed CloudWatch logs

# Retrieve admin email from environment variable
admin_email = os.environ['ADMIN_EMAIL']
# Initialize AWS DynamoDB resource to interact with the tasks table
dynamodb = boto3.resource('dynamodb')
# Reference the DynamoDB table specified in the TASKS_TABLE environment variable
table = dynamodb.Table(os.environ['TASKS_TABLE'])

# Main Lambda handler function to update task status and send notifications
def lambda_handler(event, context):
    """
    AWS Lambda handler to update the status of a task in the DynamoDB tasks table and notify assignees.
    Called via API Gateway with Cognito authentication, triggered by users updating task status.

    Args:
        event (dict): API Gateway event containing pathParameters, body, and authorizer claims.
        context (object): Lambda context object providing runtime information.

    Returns:
        dict: HTTP response with status code, CORS headers, and JSON body.
    """
    logger.info("Starting status change")

    try:
        # Extract taskId from pathParameters
        task_id = event['pathParameters']['taskId']
        # Extract user email from Cognito authorizer claims
        claims = event['requestContext']['authorizer']['claims']
        username = claims.get('email')
        # Retrieve the task from DynamoDB
        response = table.get_item(Key={'taskId': task_id})
        task = response.get('Item', {})
        # Extract assignees (list of emails) and task title
        assignees = task.get('assignedTo', [])  # List of email addresses
        title = task.get('title')
        # Parse the request body
        body = json.loads(event['body'])
        # Extract the new status from the body
        new_status = body.get('status')
        logger.info(f"TaskId: {task_id}, Body: {body}")

        # Validate the new status
        if new_status not in ['pending', 'in-progress', 'completed', 'overdue']:
            return {
                'statusCode': 400,
                'headers': cors_headers(),
                'body': json.dumps({'error': 'Invalid status'})
            }

        logger.info("updating in table")
        # Update the task status in DynamoDB
        table.update_item(
            Key={'taskId': task_id},
            UpdateExpression="SET #s = :status",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": new_status}
        )

        logger.info("returning response")
        # Send email notification to assignees and admin
        send_email(title, username, assignees)

        # Return successful response
        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps({'message': 'Task status updated'})
        }

    except Exception as e:
        # Log errors and return a 500 response
        logger.error(f"Handler error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': str(e)})
        }

# Function to send email notifications about task status changes
def send_email(task, email, recipients=[]):
    """
    Send an email notification to task assignees and the admin about a task status change.

    Args:
        task (str): Title of the task.
        email (str): Email of the user who updated the task status.
        recipients (list): List of assignee email addresses (default: empty list).

    Returns:
        bool: True if the email was sent successfully, False otherwise.
    """
    # Add admin email to recipients list
    recipients.append(admin_email)
    # Skip if no recipients
    if not recipients:
        logger.info("No recipients for email notification")
        return

    logger.info(f"In the send email function: {task, email, recipients}")

    try:
        # Retrieve Gmail credentials and SMTP settings from environment variables
        gmail_user = os.environ['GMAIL_USER']
        gmail_password = os.environ['GMAIL_PASSWORD']
        smtp_server = "smtp.gmail.com"
        smtp_port = 587

        # Create a multipart email message
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = ", ".join(recipients)  # Comma-separated list for header
        msg['Subject'] = f"Change In Status of task: {task}"
        body = f"Hello, The status of task: {task} was changed by: {email}. Log in to view the new updates"

        # Attach the plain text body
        msg.attach(MIMEText(body, 'plain'))

        # Connect to the SMTP server and send the email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()  # Enable TLS encryption
            server.login(gmail_user, gmail_password)  # Authenticate
            server.sendmail(gmail_user, recipients, msg.as_string())  # Send email
            logger.info(f"Notification sent to {recipients} for task: {task}")
            return True

    except Exception as e:
        # Log any errors during email sending
        logger.error(f"Failed to send email to {recipients}: {e}")
        return False

# Helper function to provide CORS headers for API Gateway
def cors_headers():
    """
    Return CORS headers to allow cross-origin requests from the frontend.

    Returns:
        dict: CORS headers allowing GET, OPTIONS, and PUT methods.
    """
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization,Content-Type",
        "Access-Control-Allow-Methods": "GET,OPTIONS,PUT"
    }