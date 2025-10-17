"""
Visual Analysis Agent
Uses Amazon Nova Canvas for damage assessment from satellite imagery
"""

import boto3
import numpy as np
from PIL import Image
import io
import json
import base64
from typing import Dict, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class VisualAnalysisAgent:
    """
    Agent for visual damage assessment using Nova Canvas
    """

    def __init__(self, aws_region: str = 'us-east-1'):
        """
        Initialize Visual Analysis Agent

        Args:
            aws_region: AWS region for Bedrock
        """
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        self.s3_client = boto3.client('s3', region_name=aws_region)

        logger.info(f"Initialized VisualAnalysisAgent in region {aws_region}")

    def analyze_damage(self, before_images: List[str], after_images: List[str]) -> Dict:
        """
        Use Nova Canvas for visual damage assessment

        Args:
            before_images: List of S3 keys for before images
            after_images: List of S3 keys for after images

        Returns:
            Damage assessment results
        """
        logger.info(f"Analyzing {len(before_images)} before and {len(after_images)} after images")

        results = {
            'buildings_damaged': 0,
            'roads_blocked': 0,
            'flooding_percentage': 0,
            'fire_affected_area': 0,
            'detailed_grid': [],
            'severity_map': None,
            'overall_severity': 0.0,
            'analysis_timestamp': None
        }

        if not before_images or not after_images:
            logger.warning("No images provided for analysis")
            return results

        # Process each image pair
        total_severity = 0
        processed_pairs = 0

        for before_key, after_key in zip(before_images, after_images):
            try:
                # Download images from S3
                before_img = self._download_image(before_key)
                after_img = self._download_image(after_key)

                if before_img and after_img:
                    # Use Nova Canvas for analysis
                    damage_analysis = self._invoke_nova_canvas(before_img, after_img)

                    # Aggregate results
                    if damage_analysis:
                        results['buildings_damaged'] += damage_analysis.get('buildings', {}).get('damaged_count', 0)
                        results['roads_blocked'] += damage_analysis.get('infrastructure', {}).get('blocked_roads', 0)
                        results['flooding_percentage'] = max(
                            results['flooding_percentage'],
                            damage_analysis.get('water', {}).get('flood_coverage', 0)
                        )
                        results['fire_affected_area'] += damage_analysis.get('fire', {}).get('burned_area', 0)

                        # Create detailed grid analysis
                        grid_analysis = self._create_grid_analysis(damage_analysis)
                        results['detailed_grid'].append(grid_analysis)

                        total_severity += damage_analysis.get('overall_severity', 0)
                        processed_pairs += 1

            except Exception as e:
                logger.error(f"Error processing image pair: {str(e)}")
                continue

        # Calculate overall severity
        if processed_pairs > 0:
            results['overall_severity'] = total_severity / processed_pairs

        # Generate severity heatmap
        if results['detailed_grid']:
            results['severity_map'] = self._generate_severity_map(results['detailed_grid'])

        logger.info(f"Visual analysis complete. Overall severity: {results['overall_severity']}/10")
        return results

    def _invoke_nova_canvas(self, before_image: bytes, after_image: bytes) -> Optional[Dict]:
        """
        Invoke Nova Canvas for image comparison and damage detection

        Args:
            before_image: Before image bytes
            after_image: After image bytes

        Returns:
            Damage analysis results or None
        """
        try:
            # Prepare images for Nova Canvas
            before_base64 = self._image_to_base64(before_image)
            after_base64 = self._image_to_base64(after_image)

            prompt = """
Analyze these before and after disaster satellite images.
Identify and quantify:
1. Building damage (collapsed, partially damaged, intact) - provide counts
2. Road/infrastructure damage (blocked, damaged, clear) - provide counts
3. Flooding extent (percentage of area, depth estimation)
4. Fire damage (active fires, burned areas in km²)
5. Debris fields and their extent
6. Potential locations where survivors might be trapped

Provide detailed analysis with specific counts and percentages.
Output ONLY valid JSON in this exact format:
{
    "buildings": {
        "damaged_count": <number>,
        "collapsed": <number>,
        "partially_damaged": <number>,
        "damaged_list": []
    },
    "infrastructure": {
        "blocked_roads": <number>,
        "damaged_bridges": <number>,
        "blocked_list": []
    },
    "water": {
        "flood_coverage": <percentage 0-100>,
        "flood_depth_estimate": "<string>",
        "flood_regions": []
    },
    "fire": {
        "burned_area": <number in km²>,
        "active_fires": <number>
    },
    "overall_severity": <number 0-10>
}
"""

            # Invoke Bedrock with Nova Canvas (or Claude 3 with vision)
            response = self.bedrock_client.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                body=json.dumps({
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 4000,
                    'messages': [
                        {
                            'role': 'user',
                            'content': [
                                {
                                    'type': 'image',
                                    'source': {
                                        'type': 'base64',
                                        'media_type': 'image/jpeg',
                                        'data': before_base64
                                    }
                                },
                                {
                                    'type': 'image',
                                    'source': {
                                        'type': 'base64',
                                        'media_type': 'image/jpeg',
                                        'data': after_base64
                                    }
                                },
                                {
                                    'type': 'text',
                                    'text': prompt
                                }
                            ]
                        }
                    ],
                    'temperature': 0.1
                })
            )

            # Parse response
            result = json.loads(response['body'].read())
            content = result['content'][0]['text']

            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                damage_data = json.loads(json_match.group())
                return damage_data
            else:
                logger.warning("Could not extract JSON from Nova Canvas response")
                return None

        except Exception as e:
            logger.error(f"Error invoking Nova Canvas: {str(e)}")
            return None

    def _download_image(self, s3_key: str) -> Optional[bytes]:
        """
        Download image from S3

        Args:
            s3_key: S3 object key

        Returns:
            Image bytes or None
        """
        try:
            # Extract bucket from S3 key if full path provided
            if s3_key.startswith('s3://'):
                parts = s3_key[5:].split('/', 1)
                bucket = parts[0]
                key = parts[1] if len(parts) > 1 else ''
            else:
                bucket = 'disaster-response-data-lake'
                key = s3_key

            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()

        except Exception as e:
            logger.error(f"Error downloading image {s3_key}: {str(e)}")
            return None

    def _image_to_base64(self, image_bytes: bytes) -> str:
        """
        Convert image bytes to base64 string

        Args:
            image_bytes: Image as bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(image_bytes).decode('utf-8')

    def _create_grid_analysis(self, damage_analysis: Dict) -> np.ndarray:
        """
        Create a grid-based severity analysis

        Args:
            damage_analysis: Damage analysis results

        Returns:
            NumPy array representing severity grid
        """
        # Divide area into 100x100 grid
        grid_size = 100
        severity_grid = np.zeros((grid_size, grid_size))

        try:
            # Map damage to grid cells
            buildings = damage_analysis.get('buildings', {}).get('damaged_list', [])
            for building in buildings:
                if 'coordinates' in building:
                    x, y = self._coords_to_grid(building['coordinates'], grid_size)
                    severity = building.get('severity', 5)
                    severity_grid[x, y] += severity * 2  # Building damage weighted higher

            # Add infrastructure damage
            roads = damage_analysis.get('infrastructure', {}).get('blocked_list', [])
            for road in roads:
                if 'coordinates' in road:
                    x, y = self._coords_to_grid(road['coordinates'], grid_size)
                    severity = road.get('severity', 5)
                    severity_grid[x, y] += severity * 1.5

            # Add flooding overlay
            flood_coverage = damage_analysis.get('water', {}).get('flood_coverage', 0)
            if flood_coverage > 0:
                flood_regions = damage_analysis.get('water', {}).get('flood_regions', [])
                flood_mask = self._create_flood_mask(flood_regions, grid_size)
                severity_grid += flood_mask * 1.2

            # Normalize to 0-10 scale
            if severity_grid.max() > 0:
                severity_grid = np.clip(severity_grid / severity_grid.max() * 10, 0, 10)

        except Exception as e:
            logger.error(f"Error creating grid analysis: {str(e)}")

        return severity_grid

    def _coords_to_grid(self, coordinates: Dict, grid_size: int) -> Tuple[int, int]:
        """
        Convert geographic coordinates to grid indices

        Args:
            coordinates: {'lat': float, 'lon': float}
            grid_size: Size of the grid

        Returns:
            Tuple of (x, y) grid indices
        """
        # Simplified mapping (would use proper projection in production)
        x = int((coordinates.get('lat', 0) % 1) * grid_size)
        y = int((coordinates.get('lon', 0) % 1) * grid_size)

        x = max(0, min(x, grid_size - 1))
        y = max(0, min(y, grid_size - 1))

        return x, y

    def _create_flood_mask(self, flood_regions: List, grid_size: int) -> np.ndarray:
        """
        Create flood mask for grid

        Args:
            flood_regions: List of flooded regions
            grid_size: Size of the grid

        Returns:
            NumPy array representing flood mask
        """
        mask = np.zeros((grid_size, grid_size))

        for region in flood_regions:
            if 'coordinates' in region:
                x, y = self._coords_to_grid(region['coordinates'], grid_size)
                radius = region.get('radius', 5)

                # Create circular flood region
                for i in range(max(0, x - radius), min(grid_size, x + radius)):
                    for j in range(max(0, y - radius), min(grid_size, y + radius)):
                        distance = np.sqrt((i - x)**2 + (j - y)**2)
                        if distance <= radius:
                            mask[i, j] = 1

        return mask

    def _generate_severity_map(self, grid_list: List[np.ndarray]) -> np.ndarray:
        """
        Generate aggregated severity map from multiple grids

        Args:
            grid_list: List of severity grids

        Returns:
            Aggregated severity map
        """
        if not grid_list:
            return np.zeros((100, 100))

        # Stack and average all grids
        stacked = np.stack(grid_list)
        severity_map = np.mean(stacked, axis=0)

        return severity_map
