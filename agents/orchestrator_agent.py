"""
Master Orchestrator Agent
Coordinates all sub-agents and manages disaster response workflow
"""

import boto3
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

from .visual_analysis_agent import VisualAnalysisAgent
from .resource_optimization_agent import ResourceOptimizationAgent
from .verification_agent import VerificationAgent

logger = logging.getLogger(__name__)


@dataclass
class DisasterEvent:
    """Data class for disaster event information"""
    event_id: str
    location: Dict[str, float]  # {'lat': float, 'lon': float}
    event_type: str
    severity_estimate: float
    affected_area_km2: float
    timestamp: str
    state: Optional[str] = None
    population_affected: Optional[int] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return asdict(self)


class OrchestratorAgent:
    """
    Master orchestrator that coordinates disaster response using Bedrock agents
    """

    def __init__(self, aws_region: str = 'us-east-1', knowledge_base_id: Optional[str] = None):
        """
        Initialize Orchestrator Agent

        Args:
            aws_region: AWS region for Bedrock
            knowledge_base_id: Bedrock Knowledge Base ID for historical data
        """
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        self.bedrock_agent_client = boto3.client('bedrock-agent-runtime', region_name=aws_region)
        self.s3_client = boto3.client('s3', region_name=aws_region)
        self.dynamodb = boto3.resource('dynamodb', region_name=aws_region)

        # Initialize sub-agents
        self.visual_agent = VisualAnalysisAgent(aws_region=aws_region)
        self.resource_agent = ResourceOptimizationAgent(aws_region=aws_region)
        self.verification_agent = VerificationAgent(aws_region=aws_region)

        # Knowledge base ID (created separately in AWS Console)
        self.knowledge_base_id = knowledge_base_id or "YOUR_KB_ID"

        logger.info(f"Initialized OrchestratorAgent in region {aws_region}")

    def process_disaster_event(self, event: DisasterEvent) -> Dict[str, Any]:
        """
        Main orchestration logic for disaster response

        Args:
            event: DisasterEvent object with event details

        Returns:
            Complete disaster response assessment
        """
        logger.info(f"Processing disaster event: {event.event_id}")

        try:
            # Step 1: Gather all data sources
            logger.info("Step 1: Gathering data from all sources")
            imagery_data = self._fetch_imagery_data(event)
            emergency_data = self._fetch_emergency_data(event)
            social_data = self._fetch_social_media_data(event)

            # Step 2: Visual damage assessment using Nova Canvas
            logger.info("Step 2: Performing visual damage assessment")
            visual_assessment = self.visual_agent.analyze_damage(
                before_images=imagery_data.get('before', []),
                after_images=imagery_data.get('after', [])
            )

            # Step 3: Use Bedrock for complex reasoning
            logger.info("Step 3: Running Bedrock reasoning engine")
            reasoning_prompt = self._build_reasoning_prompt(
                event=event,
                visual_assessment=visual_assessment,
                emergency_data=emergency_data,
                social_data=social_data
            )

            reasoning_response = self._invoke_bedrock_reasoning(reasoning_prompt)

            # Step 4: Generate action plan
            logger.info("Step 4: Generating action plan")
            action_plan = self._generate_action_plan(reasoning_response, visual_assessment)

            # Step 5: Optimize resource allocation
            logger.info("Step 5: Optimizing resource allocation")
            resource_allocation = self.resource_agent.optimize_allocation(
                damage_assessment=visual_assessment,
                available_resources=emergency_data.get('resources', {}),
                constraints=action_plan.get('constraints', {})
            )

            # Step 6: Cross-verify with multiple sources
            logger.info("Step 6: Cross-verifying assessment")
            verification_result = self.verification_agent.verify_assessment(
                visual_assessment=visual_assessment,
                social_reports=social_data,
                official_reports=emergency_data.get('reports', {})
            )

            # Compile final results
            result = {
                'event_id': event.event_id,
                'timestamp': datetime.now().isoformat(),
                'event_details': event.to_dict(),
                'visual_assessment': visual_assessment,
                'action_plan': action_plan,
                'resource_allocation': resource_allocation,
                'verification': verification_result,
                'confidence_score': verification_result.get('overall_confidence', 0.0),
                'processing_time_seconds': 0,  # Calculate actual time
                'status': 'COMPLETED'
            }

            logger.info(f"Successfully processed disaster event {event.event_id}")
            return result

        except Exception as e:
            logger.error(f"Error processing disaster event: {str(e)}")
            return {
                'event_id': event.event_id,
                'status': 'ERROR',
                'error_message': str(e)
            }

    def _build_reasoning_prompt(self, **kwargs) -> str:
        """
        Build complex reasoning prompt for Bedrock

        Args:
            **kwargs: event, visual_assessment, emergency_data, social_data

        Returns:
            Formatted prompt string
        """
        event = kwargs['event']
        visual = kwargs['visual_assessment']
        emergency = kwargs['emergency_data']
        social = kwargs['social_data']

        prompt = f"""
You are an emergency response coordinator AI analyzing a disaster situation.

DISASTER EVENT DETAILS:
- Event ID: {event.event_id}
- Type: {event.event_type}
- Location: Lat {event.location.get('lat')}, Lon {event.location.get('lon')}
- Estimated Severity: {event.severity_estimate}/10
- Affected Area: {event.affected_area_km2} km²
- Timestamp: {event.timestamp}

VISUAL DAMAGE ASSESSMENT:
- Buildings Damaged: {visual.get('buildings_damaged', 0)}
- Roads Blocked: {visual.get('roads_blocked', 0)}
- Flooding Extent: {visual.get('flooding_percentage', 0)}%
- Fire Damage: {visual.get('fire_affected_area', 0)} km²
- Overall Severity Score: {visual.get('overall_severity', 0)}/10

EMERGENCY RESOURCES AVAILABLE:
- Medical Teams: {emergency.get('resources', {}).get('medical_teams', 0)}
- Helicopters: {emergency.get('resources', {}).get('helicopters', 0)}
- Emergency Shelters: {emergency.get('resources', {}).get('shelters', 0)}
- Food/Water Supplies: {emergency.get('resources', {}).get('supplies_tons', 0)} tons

SOCIAL MEDIA REPORTS:
- Urgent Rescue Requests: {len(social.get('urgent_requests', []))}
- Reported Trapped Persons: {social.get('trapped_count', 0)}
- Medical Emergencies: {social.get('medical_emergencies', 0)}

Based on this information, provide a prioritized action plan with:
1. Immediate life-saving priorities (first 6 hours)
2. Critical infrastructure restoration priorities
3. Resource deployment strategy
4. Risk mitigation for secondary disasters
5. Coordination requirements between agencies

Consider ethical factors:
- Prioritize areas with highest life-threat risk
- Ensure equitable resource distribution
- Account for vulnerable populations (elderly, disabled, children)

Provide your response in JSON format with the following structure:
{{
    "immediate_priorities": [
        {{"action": "string", "location": "string", "resources_needed": [], "estimated_time": "string", "lives_at_risk": number}}
    ],
    "infrastructure_priorities": [
        {{"infrastructure_type": "string", "priority_level": number, "restoration_time": "string"}}
    ],
    "resource_deployment": {{
        "medical": {{"teams": [], "locations": []}},
        "rescue": {{"teams": [], "equipment": []}},
        "supplies": {{"distribution_points": [], "quantities": {{}}}}
    }},
    "secondary_risks": [
        {{"risk_type": "string", "probability": number, "mitigation_actions": []}}
    ],
    "coordination": {{
        "agencies": [],
        "communication_protocol": "string",
        "command_center_location": "string"
    }},
    "reasoning": "Detailed explanation of decision-making process"
}}
"""

        return prompt

    def _invoke_bedrock_reasoning(self, prompt: str) -> Dict:
        """
        Invoke Bedrock Claude for complex reasoning

        Args:
            prompt: Reasoning prompt

        Returns:
            Parsed reasoning response
        """
        try:
            response = self.bedrock_client.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                body=json.dumps({
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 4000,
                    'messages': [
                        {
                            'role': 'user',
                            'content': prompt
                        }
                    ],
                    'temperature': 0.3,  # Lower temperature for more consistent reasoning
                    'top_p': 0.9
                })
            )

            response_body = json.loads(response['body'].read())
            content = response_body['content'][0]['text']

            # Parse JSON from Claude's response
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

            logger.warning("Could not parse JSON from Bedrock response")
            return {'raw_response': content}

        except Exception as e:
            logger.error(f"Error invoking Bedrock: {str(e)}")
            return {'error': str(e)}

    def _query_knowledge_base(self, query: str) -> List[Dict]:
        """
        Query Bedrock Knowledge Base for historical patterns

        Args:
            query: Search query

        Returns:
            List of relevant documents
        """
        if not self.knowledge_base_id or self.knowledge_base_id == "YOUR_KB_ID":
            logger.warning("Knowledge base not configured")
            return []

        try:
            response = self.bedrock_agent_client.retrieve(
                knowledgeBaseId=self.knowledge_base_id,
                retrievalQuery={'text': query},
                retrievalConfiguration={
                    'vectorSearchConfiguration': {
                        'numberOfResults': 5,
                        'overrideSearchType': 'HYBRID'
                    }
                }
            )

            return response.get('retrievalResults', [])

        except Exception as e:
            logger.error(f"Error querying knowledge base: {str(e)}")
            return []

    def _fetch_imagery_data(self, event: DisasterEvent) -> Dict:
        """Fetch satellite imagery data"""
        # This would integrate with NASA connector
        return {
            'before': [],
            'after': []
        }

    def _fetch_emergency_data(self, event: DisasterEvent) -> Dict:
        """Fetch emergency resource and incident data"""
        # This would integrate with FEMA connector
        return {
            'resources': {
                'medical_teams': 15,
                'helicopters': 5,
                'shelters': 8,
                'supplies_tons': 100
            },
            'reports': {}
        }

    def _fetch_social_media_data(self, event: DisasterEvent) -> Dict:
        """Fetch social media reports"""
        # This would integrate with social media APIs
        return {
            'urgent_requests': [],
            'trapped_count': 0,
            'medical_emergencies': 0
        }

    def _generate_action_plan(self, reasoning_response: Dict, visual_assessment: Dict) -> Dict:
        """
        Generate structured action plan from reasoning response

        Args:
            reasoning_response: Bedrock reasoning output
            visual_assessment: Visual damage assessment

        Returns:
            Structured action plan
        """
        return {
            'immediate_actions': reasoning_response.get('immediate_priorities', []),
            'infrastructure_plan': reasoning_response.get('infrastructure_priorities', []),
            'deployment_strategy': reasoning_response.get('resource_deployment', {}),
            'risk_mitigation': reasoning_response.get('secondary_risks', []),
            'coordination_plan': reasoning_response.get('coordination', {}),
            'constraints': {
                'max_response_time': 6,  # hours
                'min_resource_allocation': 0.2,  # 20% minimum
                'special_considerations': ['vulnerable_populations', 'secondary_disasters']
            },
            'reasoning': reasoning_response.get('reasoning', '')
        }
