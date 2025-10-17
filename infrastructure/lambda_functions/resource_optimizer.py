"""
Lambda Function: Resource Optimizer
Optimizes resource allocation using optimization algorithms and AI
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
    Lambda handler for resource optimization

    Args:
        event: Event containing assessment and resources
        context: Lambda context

    Returns:
        Optimized resource allocation
    """
    logger.info("Resource optimization started")

    try:
        from agents.resource_optimization_agent import ResourceOptimizationAgent

        # Parse input
        event_id = event.get('event_id')
        visual_assessment = event.get('visual_assessment', {})
        action_plan = event.get('action_plan', {})
        available_resources = event.get('available_resources', {})

        # Initialize agent
        agent = ResourceOptimizationAgent(
            aws_region=os.environ.get('AWS_REGION', 'us-east-1')
        )

        # Optimize allocation
        allocation = agent.optimize_allocation(
            damage_assessment=visual_assessment,
            available_resources=available_resources,
            constraints=action_plan.get('constraints', {
                'max_response_time': 6,
                'min_resource_allocation': 0.2,
                'special_considerations': ['vulnerable_populations', 'secondary_disasters']
            })
        )

        # Add metadata
        allocation['event_id'] = event_id
        allocation['optimization_timestamp'] = context.request_id

        logger.info(f"Resource optimization complete for {len(allocation.get('zones', []))} zones")

        return {
            'statusCode': 200,
            'body': json.dumps(allocation),
            'allocation': allocation
        }

    except Exception as e:
        logger.error(f"Error in resource optimization: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'event_id': event.get('event_id', 'unknown')
            })
        }
