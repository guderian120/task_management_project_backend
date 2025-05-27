import json
import boto3
import os
from decimal import Decimal
from boto3.dynamodb.conditions import Attr


dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('Goals')
USER_GSI = 'userId-index'



"""
This function retrieves all goals for a user from the DynamoDB table.
It uses the userId from the Cognito claims to filter the goals.
"""
    
# Main Lambda handler function to fetch goals for a specific user
def lambda_handler(event, context):
    # Helper function to handle Decimal serialization for DynamoDB
    def decimal_default(obj):
        if isinstance(obj, Decimal):
            # convert to float or int as appropriate
            return float(obj)
        raise TypeError
    try:
        # Get userId from Cognito claims (from API Gateway Authorizer)
        user_id = event['requestContext']['authorizer']['claims']['sub']
        # Log the userId for debugging
        response = table.scan(
            FilterExpression=Attr('userId').eq(user_id)
        )
        print(f"Fetched goals for user {user_id}: {response['Items']}")
        # Return the goals in the response
        return {
            "statusCode": 200,
            "headers": cors_headers(),
            'body': json.dumps(response['Items'], default=decimal_default)
        }

    except Exception as e:
        print(f"Error fetching goals: {str(e)}")
        return {
            "statusCode": 500,
            "headers": cors_headers(),
            "body": json.dumps({"message": "Failed to fetch goals"})
        }



def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization,Content-Type",
        "Access-Control-Allow-Methods": "GET,OPTIONS"
    }
