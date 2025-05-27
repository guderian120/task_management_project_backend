"""
This function polls data from the Task DB and 
checks for Task whiose deadline are in three days
every task whose deadline is three days away is considered 
danger and an alert is sent to all team members on that task
"""


import boto3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from datetime import datetime, timezone, timedelta

# Initialize AWS DynamoDB resource to interact with the task table
dynamodb = boto3.resource('dynamodb')
# Reference the DynamoDB table specified in the TASK_TABLE environment variable
table = dynamodb.Table(os.environ['TASK_TABLE'])

def send_email(gmail_user, gmail_password, smtp_server, smtp_port, recipients, subject, body):
    """
    Send an email to the specified recipients using Gmail SMTP.

    Args:
        gmail_user (str): Gmail account email address used for sending emails.
        gmail_password (str): Gmail app-specific password for SMTP authentication.
        smtp_server (str): SMTP server hostname (e.g., smtp.gmail.com).
        smtp_port (int): SMTP server port (e.g., 587 for TLS).
        recipients (list): List of recipient email addresses.
        subject (str): Email subject line.
        body (str): Email body text in plain format.

    Returns:
        bool: True if the email was sent successfully, False if an error occurred.
    """
    # Create a multipart email message object
    msg = MIMEMultipart()
    # Set the sender email address
    msg['From'] = gmail_user
    # Join recipient emails into a comma-separated string for the email header
    msg['To'] = ", ".join(recipients)
    # Set the email subject
    msg['Subject'] = subject
    # Attach the plain text body to the email
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Establish a connection to the SMTP server
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            # Start TLS encryption for secure communication
            server.starttls()
            # Authenticate with the Gmail account
            server.login(gmail_user, gmail_password)
            # Send the email to all recipients
            server.sendmail(gmail_user, recipients, msg.as_string())
            # Log success to CloudWatch
            print(f"Notification sent to {recipients} for task: {subject}")
            return True
    except Exception as e:
        # Log any errors encountered during email sending
        print(f"Failed to send email to {recipients}: {e}")
        return False

def lambda_handler(event, context):
    """
    AWS Lambda handler to scan DynamoDB for tasks due within 3 days and send email reminders.

    Args:
        event (dict): Lambda event data (not used in this function).
        context (object): Lambda context object providing runtime information.

    Returns:
        None: This function does not return a value but logs results to CloudWatch.
    """
    # Get the current UTC time
    now = datetime.now(timezone.utc)
    # Define a threshold for tasks due within the next 3 days
    threshold = now + timedelta(days=3)

    # Scan the DynamoDB table to retrieve all tasks
    response = table.scan()
    # Initialize a list to store tasks with upcoming deadlines
    upcoming_tasks = []

    # Iterate through each task in the DynamoDB response
    for item in response['Items']:
        # Extract the deadline, assignees, and title from the task item
        due_date = item.get('deadline')
        assignees = item.get('assignedTo', [])  # List of email addresses
        title = item.get('title', 'Untitled Task')

        # Process tasks with a valid due date
        if due_date:
            try:
                # Convert the due date string to a datetime object
                task_due = datetime.fromisoformat(due_date)
                # Check if the task is due within the 3-day threshold
                if now < task_due <= threshold:
                    # Add the task to the upcoming tasks list
                    upcoming_tasks.append({'title': title, 'assignees': assignees, 'dueDate': due_date})
            except ValueError:
                # Log any invalid date formats
                print(f"Invalid date format: {due_date}")

    # Retrieve Gmail credentials and SMTP settings from environment variables
    GMAIL_USER = os.environ['GMAIL_USER']
    GMAIL_PASSWORD = os.environ['GMAIL_PASSWORD']
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    # Iterate through tasks with upcoming deadlines
    for task in upcoming_tasks:
        # Get the list of recipients (assignees)
        recipients = task['assignees']
        # Skip tasks with no assignees
        if not recipients:
            continue

        # Define the email subject and body
        subject = f"[UPCOMING DEADLINE] Task: {task['title']}"
        body = f"Reminder: The task '{task['title']}' is due on {task['dueDate']}. Please ensure it's completed on time."

        # Send the email using the isolated send_email function
        send_email(GMAIL_USER, GMAIL_PASSWORD, SMTP_SERVER, SMTP_PORT, recipients, subject, body)