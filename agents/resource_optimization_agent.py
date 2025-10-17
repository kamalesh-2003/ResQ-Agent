"""
Resource Optimization Agent
Optimizes resource allocation using linear programming and AI reasoning
"""

import boto3
import json
import numpy as np
from typing import Dict, List, Optional
from scipy.optimize import linprog
import logging

logger = logging.getLogger(__name__)


class ResourceOptimizationAgent:
    """
    Agent for optimizing disaster resource allocation
    """

    def __init__(self, aws_region: str = 'us-east-1'):
        """
        Initialize Resource Optimization Agent

        Args:
            aws_region: AWS region for Bedrock
        """
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        self.aws_region = aws_region

        logger.info(f"Initialized ResourceOptimizationAgent in region {aws_region}")

    def optimize_allocation(self,
                           damage_assessment: Dict,
                           available_resources: Dict,
                           constraints: Dict) -> Dict:
        """
        Optimize resource allocation using linear programming and AI reasoning

        Args:
            damage_assessment: Visual damage assessment results
            available_resources: Available resources dictionary
            constraints: Allocation constraints

        Returns:
            Optimized resource allocation plan
        """
        logger.info("Starting resource optimization")

        try:
            # Build optimization problem
            zones = self._identify_priority_zones(damage_assessment)

            if not zones:
                logger.warning("No priority zones identified")
                return {'zones': [], 'allocation': {}}

            # Create distance matrix between zones and resource locations
            distance_matrix = self._calculate_distance_matrix(
                zones,
                available_resources.get('locations', [])
            )

            # Define optimization objective (minimize response time weighted by severity)
            c = self._build_objective_function(zones, distance_matrix)

            # Define constraints
            A_ub, b_ub = self._build_constraints(zones, available_resources)

            # Solve optimization problem
            if len(c) > 0 and A_ub.shape[0] > 0:
                result = linprog(c, A_ub=A_ub, b_ub=b_ub, method='highs')

                # Parse optimization results
                initial_allocation = self._parse_optimization_results(
                    result,
                    zones,
                    available_resources
                )
            else:
                logger.warning("Insufficient data for optimization, using heuristic allocation")
                initial_allocation = self._heuristic_allocation(zones, available_resources)

            # Use Bedrock for nuanced adjustments
            refined_allocation = self._refine_with_ai(initial_allocation, zones, constraints)

            logger.info("Resource optimization complete")
            return refined_allocation

        except Exception as e:
            logger.error(f"Error in resource optimization: {str(e)}")
            return {'error': str(e), 'zones': [], 'allocation': {}}

    def _identify_priority_zones(self, damage_assessment: Dict) -> List[Dict]:
        """
        Identify priority zones from damage assessment

        Args:
            damage_assessment: Damage assessment results

        Returns:
            List of priority zones
        """
        zones = []

        try:
            severity_grid = damage_assessment.get('severity_map')

            if severity_grid is not None:
                # Find high-severity clusters
                threshold = 7.0  # Severity threshold

                high_severity_mask = severity_grid > threshold

                if np.any(high_severity_mask):
                    # Use connected components to find clusters
                    from scipy import ndimage

                    labeled_array, num_features = ndimage.label(high_severity_mask)

                    for zone_id in range(1, num_features + 1):
                        zone_mask = labeled_array == zone_id
                        zone_coords = np.where(zone_mask)

                        # Calculate zone properties
                        center_x = int(np.mean(zone_coords[0]))
                        center_y = int(np.mean(zone_coords[1]))
                        severity = float(np.mean(severity_grid[zone_mask]))
                        area = int(np.sum(zone_mask))

                        zones.append({
                            'zone_id': f"zone_{zone_id}",
                            'center': {'x': center_x, 'y': center_y},
                            'severity': severity,
                            'area_cells': area,
                            'priority': self._calculate_priority(severity, area)
                        })

            # Sort zones by priority
            zones.sort(key=lambda z: z['priority'], reverse=True)

        except Exception as e:
            logger.error(f"Error identifying priority zones: {str(e)}")

        return zones

    def _calculate_priority(self, severity: float, area: int) -> float:
        """Calculate zone priority score"""
        return severity * 0.7 + (area / 100.0) * 0.3

    def _calculate_distance_matrix(self, zones: List[Dict], resource_locations: List[Dict]) -> np.ndarray:
        """
        Calculate distance matrix between zones and resource locations

        Args:
            zones: List of priority zones
            resource_locations: List of resource location dictionaries

        Returns:
            Distance matrix
        """
        if not zones or not resource_locations:
            return np.zeros((len(zones) if zones else 1, len(resource_locations) if resource_locations else 1))

        n_zones = len(zones)
        n_locations = len(resource_locations)

        distance_matrix = np.zeros((n_zones, n_locations))

        for i, zone in enumerate(zones):
            for j, location in enumerate(resource_locations):
                # Euclidean distance (simplified)
                dx = zone['center']['x'] - location.get('x', 0)
                dy = zone['center']['y'] - location.get('y', 0)
                distance_matrix[i, j] = np.sqrt(dx**2 + dy**2)

        return distance_matrix

    def _build_objective_function(self, zones: List[Dict], distance_matrix: np.ndarray) -> np.ndarray:
        """
        Build objective function for optimization

        Args:
            zones: Priority zones
            distance_matrix: Distance matrix

        Returns:
            Objective function coefficients
        """
        # Minimize: sum of (distance * severity) for each zone
        n_zones, n_locations = distance_matrix.shape

        c = np.zeros(n_zones * n_locations)

        for i, zone in enumerate(zones):
            for j in range(n_locations):
                idx = i * n_locations + j
                c[idx] = distance_matrix[i, j] * (11 - zone['severity'])  # Inverse severity weight

        return c

    def _build_constraints(self, zones: List[Dict], available_resources: Dict) -> tuple:
        """
        Build constraint matrices for optimization

        Args:
            zones: Priority zones
            available_resources: Available resources

        Returns:
            Tuple of (A_ub, b_ub) constraint matrices
        """
        n_zones = len(zones)
        n_resources = len(available_resources.get('locations', []))

        if n_zones == 0 or n_resources == 0:
            return np.array([[1]]), np.array([0])

        # Each zone must receive at least minimum allocation
        # Each resource location has maximum capacity

        n_vars = n_zones * n_resources
        constraints = []
        bounds = []

        # Resource capacity constraints
        for j in range(n_resources):
            constraint = np.zeros(n_vars)
            for i in range(n_zones):
                constraint[i * n_resources + j] = 1
            constraints.append(constraint)
            bounds.append(available_resources.get('total_capacity', 100) / n_resources)

        A_ub = np.array(constraints) if constraints else np.array([[1] * n_vars])
        b_ub = np.array(bounds) if bounds else np.array([1])

        return A_ub, b_ub

    def _parse_optimization_results(self, result, zones: List[Dict], available_resources: Dict) -> Dict:
        """
        Parse optimization results into allocation plan

        Args:
            result: scipy.optimize result
            zones: Priority zones
            available_resources: Available resources

        Returns:
            Initial allocation plan
        """
        if not result.success:
            logger.warning("Optimization did not converge, using heuristic allocation")
            return self._heuristic_allocation(zones, available_resources)

        allocation = {
            'zones': zones,
            'resource_assignments': [],
            'optimization_status': 'success',
            'total_cost': float(result.fun)
        }

        # Parse decision variables
        x = result.x
        n_locations = len(available_resources.get('locations', []))

        for i, zone in enumerate(zones):
            zone_allocation = {
                'zone_id': zone['zone_id'],
                'severity': zone['severity'],
                'assigned_resources': []
            }

            for j in range(n_locations):
                idx = i * n_locations + j
                if x[idx] > 0.1:  # Threshold for assignment
                    zone_allocation['assigned_resources'].append({
                        'resource_location_id': j,
                        'allocation_amount': float(x[idx])
                    })

            allocation['resource_assignments'].append(zone_allocation)

        return allocation

    def _heuristic_allocation(self, zones: List[Dict], available_resources: Dict) -> Dict:
        """
        Heuristic allocation when optimization fails

        Args:
            zones: Priority zones
            available_resources: Available resources

        Returns:
            Heuristic allocation plan
        """
        allocation = {
            'zones': zones,
            'resource_assignments': [],
            'optimization_status': 'heuristic'
        }

        # Simple heuristic: allocate proportional to severity
        total_severity = sum(z['severity'] for z in zones)

        for zone in zones:
            proportion = zone['severity'] / total_severity if total_severity > 0 else 1.0 / len(zones)

            zone_allocation = {
                'zone_id': zone['zone_id'],
                'severity': zone['severity'],
                'assigned_resources': [{
                    'type': 'medical_teams',
                    'count': int(available_resources.get('medical_teams', 0) * proportion)
                }, {
                    'type': 'rescue_teams',
                    'count': int(available_resources.get('rescue_teams', 0) * proportion)
                }]
            }

            allocation['resource_assignments'].append(zone_allocation)

        return allocation

    def _refine_with_ai(self, initial_allocation: Dict, zones: List, constraints: Dict) -> Dict:
        """
        Use Bedrock to refine allocation with nuanced reasoning

        Args:
            initial_allocation: Initial allocation plan
            zones: Priority zones
            constraints: Constraints

        Returns:
            Refined allocation plan
        """
        prompt = f"""
Review and refine this disaster resource allocation plan:

INITIAL ALLOCATION:
{json.dumps(initial_allocation, indent=2)}

ZONE DETAILS:
{json.dumps(zones[:5], indent=2)}  # Limit for token efficiency

CONSTRAINTS:
- Maximum response time: {constraints.get('max_response_time', 6)} hours
- Equity requirement: No zone should receive <20% of needed resources
- Priority: Life-threatening situations first
- Special considerations: {constraints.get('special_considerations', [])}

Refine the allocation considering:
1. Secondary disaster risks (aftershocks, floods)
2. Access routes (some may be blocked)
3. Resource compatibility (medical teams need medical supplies)
4. Time-critical medical cases
5. Vulnerable populations

Provide refined allocation in JSON format with reasoning for changes.
Output format:
{{
    "refined_assignments": [],
    "adjustments_made": [],
    "reasoning": "string"
}}
"""

        try:
            response = self.bedrock_client.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                body=json.dumps({
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 3000,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.3
                })
            )

            result = json.loads(response['body'].read())
            content = result['content'][0]['text']

            # Parse JSON response
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                refinements = json.loads(json_match.group())

                # Merge refinements with initial allocation
                initial_allocation['refined_assignments'] = refinements.get('refined_assignments', [])
                initial_allocation['adjustments'] = refinements.get('adjustments_made', [])
                initial_allocation['ai_reasoning'] = refinements.get('reasoning', '')

                return initial_allocation

        except Exception as e:
            logger.error(f"Error refining with AI: {str(e)}")

        return initial_allocation
