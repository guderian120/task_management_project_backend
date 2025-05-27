# Importing necessary libraries for AWS integration, JSON handling, UUID generation, and date/time operations
import json
import uuid
import os
import boto3
from datetime import datetime
from decimal import Decimal  # Used to handle decimal numbers for DynamoDB serialization
from boto3.dynamodb.conditions import Attr  # Used for DynamoDB query conditions

# Initialize AWS DynamoDB resource to interact with the goals table
dynamodb = boto3.resource('dynamodb')
# Reference the DynamoDB table specified in the GOALS_TABLE environment variable
table = dynamodb.Table(os.environ['GOALS_TABLE'])

# Custom JSON encoder to handle Decimal types from DynamoDB
# DynamoDB stores numbers as Decimal, but JSON serialization requires conversion to int or float
class DecimalEncoder(json.JSONEncoder):
    """
    Custom JSON encoder to safely convert DynamoDB Decimal types to JSON-compatible int or float.
    
    Args:
        obj: Object to serialize (e.g., Decimal for progress field).
    
    Returns:
        int or float: Integer if the Decimal has no fractional part, float otherwise.
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to int if it has no fractional part, else to float
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

# Function to retrieve the creator (project lead) of a task from the DynamoDB tasks table
def get_task_creator(task_id):
    """
    Retrieve the creator of a task based on its taskId.
    Used to assign the task's creator as the default assignee for a goal if not specified.
    
    Args:
        task_id (str): The unique ID of the task.
    
    Returns:
        str or None: Email of the task creator, or None if not found or an error occurs.
    """
    print(f"[DEBUG] Getting creator for task: {task_id}")  # Log for CloudWatch debugging
    try:
        # Scan the tasks table to find the task with the given taskId, projecting only taskId and createdBy
        response = table.scan(
            FilterExpression=Attr('taskId').eq(task_id),
            ProjectionExpression='taskId, createdBy'
        )
        items = response.get('Items', [])
        
        # Check if the task exists
        if not items:
            print(f"[WARNING] No task found with ID: {task_id}")
            return None
        
        # Extract the creator's email from the first matching item
        creator = items[0].get('createdBy')
        print(f"[DEBUG] Found task creator: {creator}")
        return creator
    
    except Exception as e:
        # Log any errors and return None to gracefully handle failures
        print(f"[ERROR] Failed to get task creator: {str(e)}")
        return None

# Main Lambda handler function for creating or updating goals
def lambda_handler(event, context):
    """
    AWS Lambda handler to create or update goals in the DynamoDB goals table.
    Handles HTTP POST requests from API Gateway, triggered by team members via the frontend.
    
    Args:
        event (dict): API Gateway event containing the request body and authorizer claims.
        context (object): Lambda context object providing runtime information.
    
    Returns:
        dict: HTTP response with status code, CORS headers, and JSON body.
    """
    print("[DEBUG] Received event:", json.dumps(event, indent=2))  # Log event for CloudWatch debugging

    try:
        # Parse the request body as JSON, handling Decimal types for numeric fields
        body = json.loads(event['body'], parse_float=Decimal)
        # Extract user information from Cognito authorizer claims
        userId = event['requestContext']['authorizer']['claims']['sub']  # User's Cognito sub (unique ID)
        user_email = event['requestContext']['authorizer']['claims']['email']  # User's email
        # Determine the operation mode (create or update) from the request body
        mode = body.get('action', 'create')
        
        print(f"[DEBUG] Processing {mode} operation for user: {user_email}")  # Log operation details

        # Validate required fields in the request body
        required_fields = ['title', 'description', 'dueDate', 'taskId']
        for field in required_fields:
            if field not in body:
                # Return a 400 error if any required field is missing
                return response(400, {'error': f'Missing required field: {field}'})

        # Extract goal details from the request body
        title = body['title']  # Goal title (e.g., "Implement UI login Page")
        description = body['description']  # Goal description
        dueDate = body['dueDate']  # Goal deadline in ISO format
        taskId = body['taskId']  # ID of the associated task
        progress = body.get('progress', 0)  # Progress percentage, default to 0
        print(f"[DEBUG] Basic fields - Title: {title}, TaskID: {taskId}, Progress: {progress}")

        # Handle assignee for the goal
        assignee = body.get('assignee')  # Assignee email from request, if provided
        print(f"[DEBUG] Initial assignee from request: {assignee}")
        
        # If no assignee is provided, fall back to the task creator or current user
        if not assignee:
            print("[DEBUG] No assignee provided, getting task creator")
            assignee = get_task_creator(taskId)
            if not assignee:
                print("[DEBUG] No task creator found, defaulting to current user")
                assignee = user_email
                
        print(f"[DEBUG] Final assignee: {assignee}")

        # Handle update operation for existing goals
        if mode == 'update':
            goalId = body.get('goalId')  # Goal ID required for updates
            if not goalId:
                # Return a 400 error if goalId is missing for update
                return response(400, {'error': 'goalId is required for update'})

            print(f"[DEBUG] Updating goal {goalId}")

            # Build update expression for DynamoDB
            update_expr = []
            expr_attr_vals = {}
            expr_attr_names = {}
            update_fields = {
                'title': title,
                'description': description,
                'dueDate': dueDate,
                'taskId': taskId,
                'progress': progress,
                'assignee': assignee
            }

            # Construct update expression and attribute mappings
            for k, v in update_fields.items():
                update_expr.append(f"#field_{k} = :val_{k}")
                expr_attr_vals[f":val_{k}"] = v
                expr_attr_names[f"#field_{k}"] = k

            # Update the goal in DynamoDB and return the updated item
            result = table.update_item(
                Key={'goalId': goalId},
                UpdateExpression="SET " + ", ".join(update_expr),
                ExpressionAttributeValues=expr_attr_vals,
                ExpressionAttributeNames=expr_attr_names,
                ReturnValues="ALL_NEW"
            )

            print(f"[DEBUG] Update successful for goal {goalId}")
            return response(201, {'message': 'Goal updated successfully', 'goalId': goalId})

        else:  # Create mode for new goals
            # Generate a unique goal ID
            goalId = str(uuid.uuid4())
            # Record the creation timestamp in ISO format
            createdAt = datetime.utcnow().isoformat()

            # Construct the goal item for DynamoDB
            item = {
                'goalId': goalId,
                'title': title,
                'description': description,
                'dueDate': dueDate,
                'taskId': taskId,
                'userId': userId,  # Cognito user ID of the creator
                'userEmail': user_email,  # Creator's email
                'assignee': assignee,  # Assignee (task creator or user)
                'progress': progress,  # Initial progress percentage
                'createdAt': createdAt  # Creation timestamp
            }

            print(f"[DEBUG] Creating new goal with data:", json.dumps(item, indent=2))
            # Save the goal to DynamoDB
            table.put_item(Item=item)

            print(f"[DEBUG] Successfully created goal {goalId}")
            return response(201, {'message': 'Goal created successfully', 'goalId': goalId})

    except Exception as e:
        # Log unexpected errors and return a 500 response
        print(f"[ERROR] Unexpected error: {str(e)}", exc_info=True)
        return response(500, {'error': str(e)})

# Helper function to format HTTP responses with CORS headers
def response(status_code, body):
    """
    Format an HTTP response with CORS headers for API Gateway Lambda proxy integration.
    
    Args:
        status_code (int): HTTP status code (e.g., 201, 400, 500).
        body (dict): Response body to be serialized as JSON.
    
    Returns:
        dict: Formatted response with status code, CORS headers, and JSON body.
    """
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps(body, cls=DecimalEncoder)
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