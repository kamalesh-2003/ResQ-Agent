"""
Lambda Function: Visual Analysis
Processes satellite imagery using Bedrock and visual analysis agent
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
    Lambda handler for visual damage assessment

    Args:
        event: Event containing imagery data
        context: Lambda context

    Returns:
        Visual assessment results
    """
    logger.info("Visual analysis started")

    try:
        from agents.visual_analysis_agent import VisualAnalysisAgent

        # Parse input
        event_id = event.get('event_id')
        imagery_data = event.get('imagery_data', {})

        before_images = imagery_data.get('before', [])
        after_images = imagery_data.get('after', [])

        logger.info(f"Processing {len(before_images)} before and {len(after_images)} after images")

        # Initialize visual analysis agent
        agent = VisualAnalysisAgent(
            aws_region=os.environ.get('AWS_REGION', 'us-east-1')
        )

        # Perform analysis
        assessment = agent.analyze_damage(
            before_images=before_images,
            after_images=after_images
        )

        # Add metadata
        assessment['event_id'] = event_id
        assessment['analysis_timestamp'] = event['timestamp'] if 'timestamp' in event else None

        logger.info(f"Visual analysis complete. Severity: {assessment.get('overall_severity', 0)}/10")

        return {
            'statusCode': 200,
            'body': json.dumps(assessment),
            'assessment': assessment
        }

    except Exception as e:
        logger.error(f"Error in visual analysis: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'event_id': event.get('event_id', 'unknown')
            })
        }
