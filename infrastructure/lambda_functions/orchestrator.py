"""
Lambda Function: Orchestrator
Coordinates disaster response using Bedrock Claude Opus 4
"""

import json
import os
import boto3
import logging
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder for Decimal types"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def lambda_handler(event, context):
    """
    Lambda handler for orchestration using Bedrock

    Args:
        event: Event containing disaster event details
        context: Lambda context

    Returns:
        Orchestration results with action plan
    """
    logger.info(f"Orchestrator Lambda started. Event: {json.dumps(event, cls=DecimalEncoder)}")

    try:
        # Get AWS region from environment or context
        aws_region = os.environ.get('AWS_DEFAULT_REGION', 'us-west-2')

        # Initialize Bedrock client
        bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        dynamodb = boto3.resource('dynamodb', region_name=aws_region)

        # Parse input - handle Step Functions Payload wrapper
        if 'Payload' in event:
            event_data = event['Payload']
        else:
            event_data = event

        # Extract event details
        event_id = event_data.get('event_id', 'unknown')
        event_type = event_data.get('event_type', 'unknown')
        location = event_data.get('location', {})
        severity = event_data.get('severity', 5.0)
        radius_km = event_data.get('radius_km', 50)

        logger.info(f"Processing event {event_id}: {event_type} at {location}")

        # Build prompt for Bedrock Claude
        prompt = f"""You are an emergency response coordinator AI analyzing a disaster situation.

DISASTER EVENT DETAILS:
- Event ID: {event_id}
- Type: {event_type}
- Location: {location.get('city', 'Unknown')}, {location.get('state', 'Unknown')} (Lat: {location.get('lat')}, Lon: {location.get('lon')})
- Estimated Severity: {severity}/10
- Affected Area Radius: {radius_km} km
- Timestamp: {datetime.now().isoformat()}

Based on this disaster event, provide a comprehensive emergency response action plan including:

1. Immediate life-saving priorities (first 6 hours)
2. Critical infrastructure assessment and restoration priorities
3. Resource deployment strategy (medical teams, rescue equipment, supplies)
4. Risk mitigation for secondary disasters
5. Coordination requirements between agencies

Consider ethical factors:
- Prioritize areas with highest life-threat risk
- Ensure equitable resource distribution
- Account for vulnerable populations (elderly, disabled, children)

Provide your response in JSON format with the following structure:
{{
    "immediate_priorities": [
        {{"action": "string", "location": "string", "resources_needed": ["list"], "estimated_time": "string", "lives_at_risk": number}}
    ],
    "infrastructure_priorities": [
        {{"infrastructure_type": "string", "priority_level": number, "restoration_time": "string"}}
    ],
    "resource_deployment": {{
        "medical": {{"teams": number, "locations": ["list"]}},
        "rescue": {{"teams": number, "equipment": ["list"]}},
        "supplies": {{"distribution_points": ["list"], "water_liters": number, "food_meals": number}}
    }},
    "secondary_risks": [
        {{"risk_type": "string", "probability": number, "mitigation_actions": ["list"]}}
    ],
    "coordination": {{
        "agencies": ["list"],
        "communication_protocol": "string",
        "command_center_location": "string"
    }},
    "estimated_affected_population": number,
    "response_timeline_hours": number,
    "confidence_score": number,
    "reasoning": "Detailed explanation of decision-making process"
}}"""

        logger.info("Invoking Bedrock Claude Opus 4")

        # Invoke Bedrock
        response = bedrock_client.invoke_model(
            modelId='us.anthropic.claude-opus-4-20250514-v1:0',
            body=json.dumps({
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4000,
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'temperature': 0.3,
                'top_p': 0.9
            })
        )

        response_body = json.loads(response['body'].read())
        content = response_body['content'][0]['text']

        logger.info(f"Bedrock response received ({len(content)} chars)")

        # Parse JSON from response
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            action_plan = json.loads(json_match.group())
        else:
            logger.warning("Could not parse JSON from Bedrock response, using raw content")
            action_plan = {
                'raw_response': content,
                'confidence_score': 0.5
            }

        # Compile result
        result = {
            'event_id': event_id,
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'location': location,
            'severity': severity,
            'action_plan': action_plan,
            'confidence_score': action_plan.get('confidence_score', 0.7),
            'status': 'COMPLETED',
            'bedrock_model': 'claude-opus-4'
        }

        # Store result in DynamoDB
        try:
            results_table = dynamodb.Table('assessment-results')
            results_table.put_item(
                Item={
                    'event_id': event_id,
                    'assessment_type': 'ORCHESTRATION',
                    'timestamp': int(datetime.now().timestamp()),
                    'confidence_score': Decimal(str(action_plan.get('confidence_score', 0.7))),
                    'status': 'COMPLETED',
                    'results': json.dumps(result, cls=DecimalEncoder)
                }
            )
            logger.info(f"Stored orchestration results in DynamoDB for event {event_id}")
        except Exception as db_error:
            logger.error(f"Error storing to DynamoDB: {str(db_error)}")
            # Don't fail the Lambda, just log the error

        # Also update the disaster-events table
        try:
            events_table = dynamodb.Table('disaster-events')
            events_table.update_item(
                Key={
                    'event_id': event_id,
                    'timestamp': event_data.get('timestamp', int(datetime.now().timestamp()))
                },
                UpdateExpression='SET #status = :status, orchestration_complete = :complete',
                ExpressionAttributeNames={
                    '#status': 'status'
                },
                ExpressionAttributeValues={
                    ':status': 'IN_PROGRESS',
                    ':complete': True
                }
            )
            logger.info(f"Updated event status in disaster-events table")
        except Exception as update_error:
            logger.error(f"Error updating event status: {str(update_error)}")

        logger.info(f"Orchestration complete for event {event_id}")

        return {
            'statusCode': 200,
            'Payload': result,
            'action_plan': action_plan,
            'resource_allocation': action_plan.get('resource_deployment', {})
        }

    except Exception as e:
        logger.error(f"Error in orchestration: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'Payload': {
                'error': str(e),
                'event_id': event.get('event_id', 'unknown'),
                'status': 'FAILED'
            }
        }
