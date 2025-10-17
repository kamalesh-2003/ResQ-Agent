"""
Lambda Function: Data Ingestion
Handles initial data collection from all sources
"""

import json
import os
import sys
import logging
from datetime import datetime

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Add parent directory to path for imports
sys.path.append('/opt/python')


def lambda_handler(event, context):
    """
    Main Lambda handler for data ingestion

    Args:
        event: Lambda event containing disaster event details
        context: Lambda context

    Returns:
        Response with collection status
    """
    logger.info(f"Data ingestion started for event: {json.dumps(event)}")

    try:
        # Import here to avoid cold start delays
        from data_ingestion.data_pipeline import DataPipeline, DisasterEventInput

        # Parse event
        event_data = event.get('body', event) if isinstance(event.get('body'), dict) else event

        # Create disaster event input
        disaster_event = DisasterEventInput(
            event_id=event_data['event_id'],
            location=event_data['location'],
            event_type=event_data['event_type'],
            timestamp=event_data.get('timestamp', datetime.now().isoformat()),
            state=event_data.get('state'),
            radius_km=event_data.get('radius_km', 50),
            severity_estimate=event_data.get('severity_estimate')
        )

        # Initialize pipeline
        pipeline = DataPipeline(
            aws_region=os.environ.get('AWS_REGION', 'us-east-1'),
            s3_bucket=os.environ.get('S3_BUCKET', 'resq-agent-data-lake'),
            twitter_token=os.environ.get('TWITTER_BEARER_TOKEN'),
            noaa_token=os.environ.get('NOAA_API_TOKEN')
        )

        # Collect all data
        result = pipeline.collect_all_data(disaster_event)

        logger.info(f"Data collection complete. Status: {result['status']}")

        return {
            'statusCode': 200 if result['status'] in ['COMPLETED', 'PARTIAL'] else 500,
            'body': json.dumps(result),
            'headers': {
                'Content-Type': 'application/json'
            }
        }

    except Exception as e:
        logger.error(f"Error in data ingestion: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'event_id': event.get('event_id', 'unknown')
            }),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
