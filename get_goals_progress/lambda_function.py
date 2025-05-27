# Importing necessary libraries for AWS integration, JSON handling, and logging
import json
import boto3
import os
from decimal import Decimal  # Used to handle DynamoDB Decimal types for serialization
import logging
from boto3.dynamodb.conditions import Attr  # Used for DynamoDB query conditions

# Configure logging for CloudWatch analysis
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Set logging level to INFO for detailed CloudWatch logs

# Initialize AWS DynamoDB resource to interact with the goals table
dynamodb = boto3.resource('dynamodb')
# Reference the DynamoDB table specified in the GOALS_TABLE environment variable
table = dynamodb.Table(os.environ['GOALS_TABLE'])

# Main Lambda handler function to fetch goals for a specific task
def lambda_handler(event, context):
    """
    AWS Lambda handler to retrieve all goals associated with a specific task from the DynamoDB goals table.
    Restricted to admin users, called via API Gateway to support progress tracking by team leads.

    Args:
        event (dict): API Gateway event containing pathParameters with taskId.
        context (object): Lambda context object providing runtime information.

    Returns:
        dict: HTTP response with status code, CORS headers, and JSON body containing taskId and goal details.
    """
    # Helper function to handle Decimal serialization for DynamoDB
    def decimal_default(obj):
        """
        Convert DynamoDB Decimal types to JSON-compatible float for serialization.

        Args:
            obj: Object to serialize (e.g., Decimal for progress field).

        Returns:
            float: Decimal converted to float.

        Raises:
            TypeError: If the object is not a Decimal.
        """
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError

    # Log the received event for CloudWatch debugging
    logger.info("Received event: %s", json.dumps(event))

    # Extract taskId from pathParameters
    task_id = event.get('pathParameters', {}).get('taskId')
    # Validate that taskId is provided
    if not task_id:
        logger.warning("Missing taskId in path parameters")
        return {
            'statusCode': 400,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Missing taskId parameter'})
        }

    try:
        # Log the scan operation for debugging
        logger.info("Scanning table for taskId: %s", task_id)
        # Scan the goals table to retrieve all goals associated with the given taskId
        response = table.scan(
            FilterExpression=Attr('taskId').eq(task_id)
        )
        logger.info("Raw scan response: %s", response)

        # Extract goals from the response, defaulting to an empty list if none found
        goals = response.get('Items', [])
        logger.info("Found %d goals", len(goals))

        # Format goal data for the response, selecting relevant fields
        progress_info = [
            {
                'goalId': goal['goalId'],
                'title': goal.get('title'),
                'progress': goal.get('progress'),
                'dueDate': goal.get('dueDate'),
                'assignee': goal.get('assignee')
            }
            for goal in goals
        ]

        # Log the formatted response for debugging
        logger.info("Returning progress info: %s", progress_info)

        # Return a successful response with taskId and goal details
        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps({'taskId': task_id, 'goals': progress_info}, default=decimal_default)
        }

    except Exception as e:
        # Log any errors and return a 500 response
        logger.error("Error retrieving goals: %s", str(e), exc_info=True)
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': str(e)})
        }

# Helper function to provide CORS headers for API Gateway
def cors_headers():
    """
    Return CORS headers to allow cross-origin requests from the frontend.

    Returns:
        dict: CORS headers allowing POST and OPTIONS methods.
    """
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization,Content-Type",
        "Access-Control-Allow-Methods": "POST,OPTIONS"
    }

# Helper function for structured error responses (unused but included for consistency)
def error_response(status, message):
    """
    Format an error response with CORS headers.

    Args:
        status (int): HTTP status code (e.g., 400, 500).
        message (str): Error message to include in the response.

    Returns:
        dict: Formatted error response with status code, CORS headers, and JSON body.
    """
    return {
        'statusCode': status,
        'headers': cors_headers(),
        'body': json.dumps({'error': message})
    }