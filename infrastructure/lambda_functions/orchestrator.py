"""
Lambda Function: Orchestrator
Coordinates disaster response using Bedrock agents
"""

import json
import os
import sys
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

sys.path.append('/opt/python')


def lambda_handler(event, context):
    """
    Lambda handler for orchestration

    Args:
        event: Event containing all assessment data
        context: Lambda context

    Returns:
        Orchestration results with action plan
    """
    logger.info("Orchestration started")

    try:
        from agents.orchestrator_agent import OrchestratorAgent, DisasterEvent

        # Parse input
        event_data = event.get('event_data', {})
        visual_assessment = event.get('visual_assessment', {})
        collected_data = event.get('collected_data', [])

        # Extract data from parallel branches
        imagery_data = collected_data[0].get('Payload', {}) if len(collected_data) > 0 else {}
        emergency_data = collected_data[1].get('Payload', {}) if len(collected_data) > 1 else {}
        weather_data = collected_data[2].get('Payload', {}) if len(collected_data) > 2 else {}
        social_data = collected_data[3].get('Payload', {}) if len(collected_data) > 3 else {}

        # Create disaster event
        disaster_event = DisasterEvent(
            event_id=event_data.get('event_id'),
            location=event_data.get('location', {}),
            event_type=event_data.get('event_type', 'unknown'),
            severity_estimate=visual_assessment.get('overall_severity', 5.0),
            affected_area_km2=event_data.get('radius_km', 50) ** 2 * 3.14159,
            timestamp=event_data.get('timestamp'),
            state=event_data.get('state'),
            population_affected=None
        )

        # Initialize orchestrator
        agent = OrchestratorAgent(
            aws_region=os.environ.get('AWS_REGION', 'us-east-1'),
            knowledge_base_id=os.environ.get('BEDROCK_KB_ID')
        )

        # Override data fetching methods to use pre-collected data
        agent._fetch_imagery_data = lambda e: imagery_data
        agent._fetch_emergency_data = lambda e: emergency_data
        agent._fetch_social_media_data = lambda e: social_data

        # Process event
        result = agent.process_disaster_event(disaster_event)

        logger.info(f"Orchestration complete. Confidence: {result.get('confidence_score', 0)}")

        return {
            'statusCode': 200,
            'body': json.dumps(result),
            'action_plan': result.get('action_plan', {}),
            'resource_allocation': result.get('resource_allocation', {})
        }

    except Exception as e:
        logger.error(f"Error in orchestration: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'event_id': event.get('event_id', 'unknown')
            })
        }
