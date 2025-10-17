"""
NASA Satellite Imagery Connector
Fetches satellite imagery from NASA GIBS, MODIS, and Sentinel-2 sources
"""

import requests
import boto3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
import base64

logger = logging.getLogger(__name__)


class NASAImageryConnector:
    """
    Connector for fetching satellite imagery from NASA data sources
    """

    def __init__(self, aws_region: str = 'us-east-1', s3_bucket: str = 'disaster-response-data-lake'):
        """
        Initialize NASA Imagery Connector

        Args:
            aws_region: AWS region for S3 storage
            s3_bucket: S3 bucket name for storing imagery
        """
        self.s3_client = boto3.client('s3', region_name=aws_region)
        self.bucket = s3_bucket

        # NASA Worldview/GIBS endpoints
        self.gibs_endpoint = "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi"
        self.modis_endpoint = "https://modis.ornl.gov/rst/api/v1/"

        logger.info(f"Initialized NASAImageryConnector with bucket: {s3_bucket}")

    def fetch_satellite_imagery(self,
                               location: Dict[str, float],
                               event_date: datetime,
                               days_before: int = 7) -> Tuple[List[str], List[str]]:
        """
        Fetch before/after satellite imagery for a location

        Args:
            location: {'lat': float, 'lon': float, 'radius_km': float}
            event_date: Date of disaster event
            days_before: Days of imagery to fetch before event

        Returns:
            Tuple of (before_images_s3_keys, after_images_s3_keys)
        """
        logger.info(f"Fetching satellite imagery for location: {location}, event_date: {event_date}")

        # Calculate bounding box from center point and radius
        bbox = self._calculate_bbox(location['lat'], location['lon'], location.get('radius_km', 50))

        before_images = []
        after_images = []

        # Fetch imagery for date ranges
        for day_offset in range(days_before):
            try:
                # Before imagery
                before_date = event_date - timedelta(days=day_offset+1)
                before_image = self._fetch_modis_image(bbox, before_date)
                if before_image:
                    s3_key = f"imagery/before/{event_date.isoformat()}/{before_date.isoformat()}.tif"
                    self._upload_to_s3(before_image, s3_key)
                    before_images.append(s3_key)
                    logger.info(f"Fetched before image for {before_date.isoformat()}")

                # After imagery
                after_date = event_date + timedelta(days=day_offset)
                after_image = self._fetch_modis_image(bbox, after_date)
                if after_image:
                    s3_key = f"imagery/after/{event_date.isoformat()}/{after_date.isoformat()}.tif"
                    self._upload_to_s3(after_image, s3_key)
                    after_images.append(s3_key)
                    logger.info(f"Fetched after image for {after_date.isoformat()}")

            except Exception as e:
                logger.error(f"Error fetching imagery for day offset {day_offset}: {str(e)}")
                continue

        # Also fetch high-resolution Sentinel-2 if available
        try:
            sentinel_images = self._fetch_sentinel2_imagery(bbox, event_date)
            before_images.extend(sentinel_images.get('before', []))
            after_images.extend(sentinel_images.get('after', []))
        except Exception as e:
            logger.warning(f"Could not fetch Sentinel-2 imagery: {str(e)}")

        return before_images, after_images

    def _fetch_modis_image(self, bbox: List[float], date: datetime) -> Optional[bytes]:
        """
        Fetch MODIS imagery from NASA GIBS

        Args:
            bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
            date: Date to fetch imagery for

        Returns:
            Image bytes or None if fetch fails
        """
        params = {
            'request': 'GetMap',
            'service': 'WMTS',
            'layers': 'MODIS_Terra_CorrectedReflectance_TrueColor',
            'format': 'image/tiff',
            'time': date.strftime('%Y-%m-%d'),
            'bbox': ','.join(map(str, bbox)),
            'srs': 'EPSG:4326',
            'width': 2048,
            'height': 2048,
            'version': '1.3.0'
        }

        try:
            response = requests.get(self.gibs_endpoint, params=params, timeout=30)
            if response.status_code == 200 and len(response.content) > 1000:  # Ensure valid image
                return response.content
            else:
                logger.warning(f"Failed to fetch MODIS image: status {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching MODIS image: {str(e)}")
            return None

    def _fetch_sentinel2_imagery(self, bbox: List[float], event_date: datetime) -> Dict[str, List[str]]:
        """
        Fetch Sentinel-2 high-resolution imagery from AWS Open Data

        Args:
            bbox: Bounding box coordinates
            event_date: Event date for before/after comparison

        Returns:
            Dictionary with 'before' and 'after' lists of S3 keys
        """
        # Sentinel-2 integration would require sentinelhub library
        # Placeholder implementation
        logger.info("Sentinel-2 imagery fetch requested (requires additional configuration)")

        # This would use the sentinelhub library in production:
        # from sentinelhub import SHConfig, SentinelHubRequest, DataCollection, BBox, CRS

        return {'before': [], 'after': []}

    def _calculate_bbox(self, lat: float, lon: float, radius_km: float) -> List[float]:
        """
        Calculate bounding box from center point and radius

        Args:
            lat: Latitude of center point
            lon: Longitude of center point
            radius_km: Radius in kilometers

        Returns:
            Bounding box [min_lon, min_lat, max_lon, max_lat]
        """
        # Approximate conversion (1 degree ≈ 111 km at equator)
        lat_offset = radius_km / 111.0
        lon_offset = radius_km / (111.0 * abs(max(min(lat, 89), -89)))

        return [
            lon - lon_offset,  # min_lon
            lat - lat_offset,  # min_lat
            lon + lon_offset,  # max_lon
            lat + lat_offset   # max_lat
        ]

    def _upload_to_s3(self, data: bytes, s3_key: str) -> bool:
        """
        Upload data to S3

        Args:
            data: Binary data to upload
            s3_key: S3 object key

        Returns:
            True if successful, False otherwise
        """
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=data,
                ContentType='image/tiff'
            )
            logger.info(f"Uploaded image to s3://{self.bucket}/{s3_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload to S3: {str(e)}")
            return False

    def get_imagery_url(self, s3_key: str, expiration: int = 3600) -> str:
        """
        Generate presigned URL for accessing imagery

        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds

        Returns:
            Presigned URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return ""
