"""
This function is to delete a goal that is created for whatever reasons, 
Although this action is strictly not recommended
"""

# import neccessary libraries
import json
import os
import boto3


# initialize our clients
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['GOALS_TABLE'])


#main lambda function that gets invoked on api call
def lambda_handler(event, context):
    http_method = event['httpMethod']   # get the method that is being called to the api
    
    if http_method == 'DELETE': # if the method is authorized, proceed to delete the goals
        return handle_delete(event)
    else: # else return 403
        return {
            'statusCode': 405,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Method Not Allowed'})
        }
    


# function to delete a goal

def handle_delete(event):
    try:
        goalId = event['pathParameters']['goalId'] # getting the goal ID that is sent from the front end
        # delete goals and send a success response
        table.delete_item(
            Key={'goalId': goalId}
        )

        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps({'message': f'Goal {goalId} deleted successfully'})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': str(e)})
        }



# I am using the lambda proxy intergration, I cannot configure method intergration and response for cors
# So it has to be handled in the code

# This ensures that lambda accepts cors request and provides a preflight response to the front end
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Authorization,Content-Type",
        "Access-Control-Allow-Methods": "POST,DELETE,OPTIONS"
    }
