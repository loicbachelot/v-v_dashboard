import os
import json
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')


def lambda_handler(event, context):
    table = dynamodb.Table(os.environ['TABLE_NAME'])

    # CORS headers - can be defined once at the start
    cors_headers = {
        'Access-Control-Allow-Origin': '*',  # For production, replace with specific domain
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS',
        'Content-Type': 'application/json'
    }

    try:
        # Handle OPTIONS request for CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({'message': 'CORS preflight success'})
            }

        params = event.get('queryStringParameters', {})
        if not params or not params.get('userId') or not params.get('fileId'):
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'error': 'Missing userId or fileId'})
            }

        response = table.get_item(
            Key={
                'userId': params['userId'],
                'fileId': params['fileId']
            }
        )

        print("Full DynamoDB response:", response)  # Add this right after get_item()
        print("Item contents:", response.get('Item'))

        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps(response.get('Item', {}))
        }

    except ClientError as e:
        print(f"DynamoDB error: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': 'Database error'})
        }
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'error': 'Internal server error'})
        }