import os
import json
import boto3
from botocore.exceptions import ClientError
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

SECRET_NAME = "gymbo/secrets"
REGION_NAME = "us-west-1"  

def load_secrets():
    try:
        client = boto3.client("secretsmanager", region_name=REGION_NAME)
        response = client.get_secret_value(SecretId=SECRET_NAME)
        if "SecretString" in response:
            return json.loads(response["SecretString"])
    except ClientError as e:
        print(f"Error retrieving secret {SECRET_NAME} from Secrets Manager: {e}")
        raise e

# CRITICAL: Load secrets ONCE at the module level (cached for warm starts)
SECRETS = load_secrets()
DISCORD_PUBLIC_KEY = SECRETS.get("DISCORD_PUBLIC_KEY")

def verify_signature(event):
    """Verifies that the request came from Discord."""
    import base64
    
    headers = event.get('headers', {})
    # Look up headers case-insensitively to support both API Gateway REST and HTTP APIs
    signature = (headers.get('x-signature-ed25519') or 
                 headers.get('X-Signature-Ed25519') or 
                 headers.get('X-Signature-ED25519'))
    timestamp = (headers.get('x-signature-timestamp') or 
                 headers.get('X-Signature-Timestamp'))
    
    body = event.get('body', '')

    if not signature or not timestamp:
        return False

    # Decode body if API Gateway base64-encodes it
    if event.get('isBase64Encoded', False):
        try:
            body = base64.b64decode(body).decode('utf-8')
        except Exception:
            return False

    verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
    try:
        verify_key.verify(f"{timestamp}{body}".encode(), bytes.fromhex(signature))
        return True
    except BadSignatureError:
        return False

def lambda_handler(event, context):
    # 1. Verify the signature
    if not verify_signature(event):
        return {
            'statusCode': 401,
            'body': json.dumps('invalid request signature')
        }

    # Parse the request body
    body = json.loads(event.get('body', '{}'))
    interaction_type = body.get('type')

    # 2. Handle Discord's validation PING
    if interaction_type == 1:
        return {
            'statusCode': 200,
            'body': json.dumps({'type': 1})  # Respond with PONG
        }

    # 3. Handle Slash Commands (Interaction Type 2)
    if interaction_type == 2:
        command_name = body.get('data', {}).get('name')
        
        if command_name == "ping":
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'type': 4,
                    'data': {
                        'content': 'Pong! 🏓'
                    }
                })
            }
            
        elif command_name == "hello":
            user_name = body.get('member', {}).get('user', {}).get('username', 'there')
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'type': 4,
                    'data': {
                        'content': f'Hello, {user_name}! 👋'
                    }
                })
            }

    return {
        'statusCode': 400,
        'body': json.dumps('unknown interaction')
    }
