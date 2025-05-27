# Importing necessary libraries for AWS integration, JSON handling, and logging
import json
import boto3
import os
import logging
from boto3.dynamodb.conditions import Attr  # Used for DynamoDB query conditions

# Configure logging for CloudWatch analysis
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)  # Set logging level to DEBUG for detailed CloudWatch logs

# Initialize AWS DynamoDB resource to interact with the tasks table
dynamodb = boto3.resource('dynamodb')
# Reference the DynamoDB table specified in the TASKS_TABLE environment variable
table = dynamodb.Table(os.environ['TASKS_TABLE'])

# Helper function to retrieve tasks from DynamoDB with optional filtering
def get_all_tasks(filter_expression=None):
    """
    Retrieve tasks from the DynamoDB tasks table, with optional filtering.
    Supports pagination to handle large datasets.

    Args:
        filter_expression (Attr, optional): DynamoDB filter expression to apply (e.g., for user-specific tasks).

    Returns:
        list: List of task items retrieved from DynamoDB.

    Raises:
        Exception: If the scan operation fails, re-raises the error after logging.
    """
    tasks = []  # Initialize list to store retrieved tasks
    kwargs = {}  # Initialize kwargs for scan operation

    # Apply filter expression if provided
    if filter_expression:
        kwargs['FilterExpression'] = filter_expression

    while True:
        try:
            # Perform a scan operation on the tasks table
            response = table.scan(**kwargs)
            # Append retrieved items to the tasks list
            tasks.extend(response.get('Items', []))

            # Check for pagination
            if 'LastEvaluatedKey' in response:
                # Set the starting key for the next page
                kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
                logger.info("Fetching additional page of results...")
            else:
                # Exit loop if no more pages
                break
        except Exception as e:
            # Log scan errors and re-raise
            logger.error(f"Scan error: {str(e)}")
            raise

    logger.info(f"Total tasks retrieved: {len(tasks)}")
    return tasks

# Main Lambda handler function to fetch tasks based on user role
def lambda_handler(event, context):
    """
    AWS Lambda handler to retrieve tasks from the DynamoDB tasks table.
    Admins retrieve all tasks; team members retrieve only tasks assigned to them.
    Called via API Gateway with Cognito authentication.

    Args:
        event (dict): API Gateway event containing authorizer claims.
        context (object): Lambda context object providing runtime information.

    Returns:
        dict: HTTP response with status code, CORS headers, and JSON body containing tasks.
    """
    logger.info("Starting script")

    try:
        # Extract user information from Cognito authorizer claims
        claims = event['requestContext']['authorizer']['claims']
        username = claims['email']  # User's email
        groups = claims.get('cognito:groups', [])  # Cognito groups (e.g., Admin)

        # Handle groups as a string (if returned as comma-separated)
        if isinstance(groups, str):
            groups = groups.split(',') if groups else []

        # Determine if the user is an admin
        is_admin = 'Admin' in groups
        logger.info(f"User: {username}, Admin: {is_admin}")

        # Fetch tasks based on user role
        if is_admin:
            # Admins get all tasks without filtering
            tasks = get_all_tasks()
        else:
            # Team members get tasks where their email is in the assignedTo list
            filter_expr = Attr('assignedTo').contains(username)
            tasks = get_all_tasks(filter_expression=filter_expr)
            logger.info(f"Found {len(tasks)} tasks for user {username}")

        # Return successful response with tasks
        return {
            'statusCode': 200,
            'headers': {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Authorization,Content-Type",
                "Access-Control-Allow-Methods": "GET,OPTIONS"
            },
            'body': json.dumps({'tasks': tasks})
        }

    except Exception as e:
        # Log errors and return a 500 response
        logger.error(f"Handler error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {"Access-Control-Allow-Origin": "*"},
            'body': json.dumps({'error': str(e)})
        }