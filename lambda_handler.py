import os
import json
from datetime import datetime
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

def get_workout_for_split(user_id, split_name):
    """Fetches the user's workout template for a specific split from DynamoDB, falling back to a default template if not found or on error."""
    split_name = split_name.capitalize()
    table_name = os.environ.get("DYNAMODB_TABLE", "gymbo_workouts")
    current_date = datetime.utcnow().strftime("%Y-%m-%d")
    
    # Define default templates for each split
    default_templates = {
        "Push": (
            f"Push Day ({current_date})\n\n"
            "• smith bench: weight x amount of reps\n"
            "• smith incline bench: weight x amount of reps\n"
            "• pec dec fly: weight x amount of reps\n"
            "• single arm tri: weight x amount of reps"
        ),
        "Pull": (
            f"Pull Day ({current_date})\n\n"
            "• lat pulldown: weight x amount of reps\n"
            "• seated cable row: weight x amount of reps\n"
            "• face pulls: weight x amount of reps\n"
            "• bicep curls: weight x amount of reps"
        ),
        "Legs": (
            f"Legs Day ({current_date})\n\n"
            "• squat: weight x amount of reps\n"
            "• leg press: weight x amount of reps\n"
            "• lying leg curl: weight x amount of reps\n"
            "• standing calf raise: weight x amount of reps"
        ),
        "Focus": (
            f"Focus Day ({current_date})\n\n"
            "• incline dumbbell press: weight x amount of reps\n"
            "• lateral raise: weight x amount of reps\n"
            "• tricep overhead extension: weight x amount of reps\n"
            "• hammer curls: weight x amount of reps"
        )
    }
    
    default_template = default_templates.get(split_name, f"{split_name} Day ({current_date})")
    
    try:
        dynamodb = boto3.resource("dynamodb", region_name=REGION_NAME)
        table = dynamodb.Table(table_name)
        response = table.get_item(
            Key={
                "PK": f"USER#{user_id}",
                "SK": "ROUTINE"
            }
        )
        item = response.get("Item")
        if not item:
            print(f"No routine found for user {user_id}. Using default template.")
            return default_template
            
        splits = item.get("splits", {})
        exercises = splits.get(split_name)
        if not exercises:
            print(f"No {split_name} day split found in routine for user {user_id}. Using default template.")
            return default_template
            
        lines = [f"{split_name} Day ({current_date})", ""]
        for ex in exercises:
            name = ex.get("exercise_name") or ex.get("name") or "unknown exercise"
            sets = ex.get("sets", [])
            if not sets:
                lines.append(f"• {name}: weight x amount of reps")
            else:
                set_strings = []
                for s in sets:
                    w = s.get("weight_lbs") or s.get("weight") or "weight"
                    r = s.get("reps") or s.get("amount of reps") or "amount of reps"
                    set_strings.append(f"{w} x {r}")
                sets_str = ", ".join(set_strings) if set_strings else "weight x amount of reps"
                lines.append(f"• {name}: {sets_str}")
                
        return "\n".join(lines)
        
    except Exception as e:
        print(f"Error fetching {split_name} split from DynamoDB table {table_name}: {e}. Using default template.")
        return default_template


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
            
        elif command_name in ["push", "pull", "legs", "focus"]:
            user_id = (body.get('member', {}).get('user', {}).get('id') or 
                       body.get('user', {}).get('id') or 
                       'default_user')
            workout_text = get_workout_for_split(user_id, command_name)
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'type': 4,
                    'data': {
                        'content': workout_text
                    }
                })
            }

    return {
        'statusCode': 400,
        'body': json.dumps('unknown interaction')
    }
