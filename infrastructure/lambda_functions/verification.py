"""
Lambda Function: Verification
Cross-verifies assessments using multiple data sources
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
    Lambda handler for verification

    Args:
        event: Event containing assessments to verify
        context: Lambda context

    Returns:
        Verification results with confidence scores
    """
    logger.info("Verification started")

    try:
        from agents.verification_agent import VerificationAgent

        # Parse input
        event_id = event.get('event_id')
        visual_assessment = event.get('visual_assessment', {})
        social_reports = event.get('social_reports', {})
        official_reports = event.get('official_reports', {})

        # Initialize agent
        agent = VerificationAgent(
            aws_region=os.environ.get('AWS_REGION', 'us-east-1')
        )

        # Verify assessment
        verification = agent.verify_assessment(
            visual_assessment=visual_assessment,
            social_reports=social_reports,
            official_reports=official_reports
        )

        # Add metadata
        verification['event_id'] = event_id
        verification['verification_timestamp'] = context.request_id

        logger.info(f"Verification complete. Confidence: {verification.get('overall_confidence', 0):.2f}")

        return {
            'statusCode': 200,
            'body': json.dumps(verification),
            'overall_confidence': verification.get('overall_confidence', 0),
            'recommendation': verification.get('recommendation', '')
        }

    except Exception as e:
        logger.error(f"Error in verification: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'event_id': event.get('event_id', 'unknown')
            })
        }
