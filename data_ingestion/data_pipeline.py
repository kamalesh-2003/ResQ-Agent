"""
Data Pipeline Orchestrator
Coordinates data collection from all sources and prepares data for agent processing
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json
import boto3

from .api_connectors.nasa_connector import NASAImageryConnector
from .api_connectors.fema_connector import FEMADataConnector
from .api_connectors.noaa_connector import NOAAWeatherConnector
from .api_connectors.social_media_connector import SocialMediaConnector

logger = logging.getLogger(__name__)


@dataclass
class DisasterEventInput:
    """Input data for disaster event"""
    event_id: str
    location: Dict[str, float]  # {'lat': float, 'lon': float}
    event_type: str
    timestamp: str
    state: Optional[str] = None
    radius_km: float = 50
    severity_estimate: Optional[float] = None


class DataPipeline:
    """
    Orchestrates data collection from multiple sources for disaster response
    """

    def __init__(self,
                 aws_region: str = 'us-east-1',
                 s3_bucket: str = 'disaster-response-data-lake',
                 twitter_token: Optional[str] = None,
                 noaa_token: Optional[str] = None):
        """
        Initialize Data Pipeline

        Args:
            aws_region: AWS region for services
            s3_bucket: S3 bucket for data storage
            twitter_token: Twitter API bearer token
            noaa_token: NOAA API token
        """
        self.aws_region = aws_region
        self.s3_bucket = s3_bucket

        # Initialize all data connectors
        self.nasa_connector = NASAImageryConnector(
            aws_region=aws_region,
            s3_bucket=s3_bucket
        )
        self.fema_connector = FEMADataConnector()
        self.noaa_connector = NOAAWeatherConnector(api_token=noaa_token)
        self.social_connector = SocialMediaConnector(twitter_bearer_token=twitter_token)

        # AWS clients
        self.s3_client = boto3.client('s3', region_name=aws_region)
        self.dynamodb = boto3.resource('dynamodb', region_name=aws_region)

        logger.info(f"Initialized DataPipeline in region {aws_region}")

    def collect_all_data(self, event: DisasterEventInput) -> Dict:
        """
        Collect data from all sources for a disaster event

        Args:
            event: DisasterEventInput with event details

        Returns:
            Dictionary with all collected data
        """
        logger.info(f"Starting data collection for event: {event.event_id}")

        event_date = datetime.fromisoformat(event.timestamp)

        result = {
            'event_id': event.event_id,
            'collection_timestamp': datetime.now().isoformat(),
            'status': 'IN_PROGRESS',
            'data': {
                'imagery': {},
                'emergency': {},
                'weather': {},
                'social': {}
            },
            'errors': []
        }

        # 1. Fetch satellite imagery
        try:
            logger.info("Fetching satellite imagery...")
            before_images, after_images = self.nasa_connector.fetch_satellite_imagery(
                location={
                    'lat': event.location['lat'],
                    'lon': event.location['lon'],
                    'radius_km': event.radius_km
                },
                event_date=event_date,
                days_before=7
            )

            result['data']['imagery'] = {
                'before': before_images,
                'after': after_images,
                'total_images': len(before_images) + len(after_images)
            }
            logger.info(f"Retrieved {len(before_images)} before and {len(after_images)} after images")

        except Exception as e:
            error_msg = f"Error fetching imagery: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)

        # 2. Fetch FEMA data
        try:
            logger.info("Fetching FEMA data...")
            emergency_data = self._fetch_fema_data(event)
            result['data']['emergency'] = emergency_data
            logger.info(f"Retrieved FEMA data with {len(emergency_data.get('declarations', []))} declarations")

        except Exception as e:
            error_msg = f"Error fetching FEMA data: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)

        # 3. Fetch weather data
        try:
            logger.info("Fetching weather data...")
            weather_data = self._fetch_weather_data(event, event_date)
            result['data']['weather'] = weather_data
            logger.info(f"Retrieved weather data with {len(weather_data.get('storm_events', []))} events")

        except Exception as e:
            error_msg = f"Error fetching weather data: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)

        # 4. Fetch social media data
        try:
            logger.info("Fetching social media data...")
            social_data = self._fetch_social_data(event)
            result['data']['social'] = social_data
            logger.info(f"Retrieved {social_data.get('total_reports', 0)} social media reports")

        except Exception as e:
            error_msg = f"Error fetching social media: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)

        # Update status
        if len(result['errors']) == 0:
            result['status'] = 'COMPLETED'
        elif len(result['errors']) < 4:
            result['status'] = 'PARTIAL'
        else:
            result['status'] = 'FAILED'

        # Store in DynamoDB
        self._store_in_dynamodb(result)

        # Store summary in S3
        self._store_in_s3(result)

        logger.info(f"Data collection complete for {event.event_id}. Status: {result['status']}")
        return result

    def _fetch_fema_data(self, event: DisasterEventInput) -> Dict:
        """Fetch FEMA emergency data"""
        data = {
            'declarations': [],
            'shelters': [],
            'resources': {},
            'reports': {}
        }

        if event.state:
            # Fetch disaster declarations
            declarations_df = self.fema_connector.fetch_disaster_declarations(
                state=event.state,
                incident_type=event.event_type,
                limit=50
            )

            if not declarations_df.empty:
                data['declarations'] = declarations_df.to_dict('records')

            # Fetch shelter data
            shelters = self.fema_connector.fetch_shelter_data(event.state)
            data['shelters'] = shelters

            # Estimate available resources based on historical data
            data['resources'] = self._estimate_resources(event, len(shelters))

        return data

    def _fetch_weather_data(self, event: DisasterEventInput, event_date: datetime) -> Dict:
        """Fetch weather and storm data"""
        data = {
            'storm_events': [],
            'weather_alerts': [],
            'hurricane_data': []
        }

        # Fetch storm events
        date_range = (event_date - timedelta(days=7), event_date + timedelta(days=1))
        storm_events_df = self.noaa_connector.fetch_storm_events(
            location=event.location,
            date_range=date_range
        )

        if not storm_events_df.empty:
            data['storm_events'] = storm_events_df.to_dict('records')

        # Fetch severe weather alerts
        if event.state:
            alerts = self.noaa_connector.fetch_severe_weather_alerts(event.state)
            data['weather_alerts'] = alerts

        # Fetch hurricane data if applicable
        if 'hurricane' in event.event_type.lower() or 'tropical' in event.event_type.lower():
            hurricane_df = self.noaa_connector.fetch_hurricane_data(year=event_date.year)
            if not hurricane_df.empty:
                data['hurricane_data'] = hurricane_df.to_dict('records')

        return data

    def _fetch_social_data(self, event: DisasterEventInput) -> Dict:
        """Fetch social media reports"""
        # Get relevant keywords for event type
        keywords = self.social_connector.get_disaster_keywords(event.event_type)

        # Fetch tweets
        tweets_df = self.social_connector.fetch_disaster_tweets(
            location=event.location,
            keywords=keywords,
            radius_km=event.radius_km,
            max_results=100
        )

        # Analyze reports
        analysis = self.social_connector.analyze_social_reports(tweets_df)

        # Add raw tweets
        analysis['raw_tweets'] = tweets_df.to_dict('records') if not tweets_df.empty else []
        analysis['total_reports'] = len(tweets_df)

        return analysis

    def _estimate_resources(self, event: DisasterEventInput, shelter_count: int) -> Dict:
        """Estimate available resources based on event and infrastructure"""
        # This is a simplified estimation
        # In production, this would query actual resource databases

        severity = event.severity_estimate or 5.0

        # Scale resources based on severity and available shelters
        base_multiplier = severity / 5.0
        shelter_multiplier = max(1, shelter_count / 10)

        resources = {
            'medical_teams': int(15 * base_multiplier * shelter_multiplier),
            'rescue_teams': int(10 * base_multiplier),
            'helicopters': int(5 * base_multiplier),
            'ambulances': int(20 * base_multiplier * shelter_multiplier),
            'shelters': shelter_count,
            'supplies_tons': int(100 * base_multiplier * shelter_multiplier),
            'personnel': int(200 * base_multiplier * shelter_multiplier),
            'locations': self._generate_resource_locations(event, shelter_count)
        }

        return resources

    def _generate_resource_locations(self, event: DisasterEventInput, count: int) -> List[Dict]:
        """Generate resource location coordinates"""
        import random

        locations = []
        center_lat = event.location['lat']
        center_lon = event.location['lon']

        for i in range(min(count, 10)):
            # Generate locations around the center point
            offset_lat = random.uniform(-0.1, 0.1)
            offset_lon = random.uniform(-0.1, 0.1)

            locations.append({
                'id': f"resource_location_{i}",
                'x': int((center_lat + offset_lat) * 100) % 100,  # Grid coordinates
                'y': int((center_lon + offset_lon) * 100) % 100,
                'lat': center_lat + offset_lat,
                'lon': center_lon + offset_lon,
                'type': 'emergency_staging_area'
            })

        return locations

    def _store_in_dynamodb(self, result: Dict) -> None:
        """Store collection results in DynamoDB"""
        try:
            table = self.dynamodb.Table('disaster-events')

            item = {
                'event_id': result['event_id'],
                'timestamp': int(datetime.now().timestamp()),
                'collection_timestamp': result['collection_timestamp'],
                'status': result['status'],
                'imagery_count': result['data']['imagery'].get('total_images', 0),
                'declarations_count': len(result['data']['emergency'].get('declarations', [])),
                'shelters_count': len(result['data']['emergency'].get('shelters', [])),
                'social_reports_count': result['data']['social'].get('total_reports', 0),
                'errors': result['errors'],
                'data_summary': json.dumps(result)  # Store full data as JSON
            }

            table.put_item(Item=item)
            logger.info(f"Stored data collection results in DynamoDB for {result['event_id']}")

        except Exception as e:
            logger.error(f"Error storing in DynamoDB: {str(e)}")

    def _store_in_s3(self, result: Dict) -> None:
        """Store collection results in S3"""
        try:
            s3_key = f"pipeline/collections/{result['event_id']}/{result['collection_timestamp']}.json"

            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json.dumps(result, indent=2),
                ContentType='application/json'
            )

            logger.info(f"Stored data collection results in S3: s3://{self.s3_bucket}/{s3_key}")

        except Exception as e:
            logger.error(f"Error storing in S3: {str(e)}")

    def get_collected_data(self, event_id: str) -> Optional[Dict]:
        """
        Retrieve previously collected data

        Args:
            event_id: Event ID to retrieve

        Returns:
            Collected data dictionary or None
        """
        try:
            table = self.dynamodb.Table('disaster-events')
            response = table.get_item(Key={'event_id': event_id})

            if 'Item' in response:
                return json.loads(response['Item']['data_summary'])

            return None

        except Exception as e:
            logger.error(f"Error retrieving data: {str(e)}")
            return None
