"""
Verification Agent
Cross-verifies disaster assessments using multiple data sources
"""

import boto3
import json
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class VerificationAgent:
    """
    Agent for cross-verifying disaster assessments
    """

    def __init__(self, aws_region: str = 'us-east-1'):
        """
        Initialize Verification Agent

        Args:
            aws_region: AWS region for Bedrock
        """
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=aws_region)
        self.aws_region = aws_region

        logger.info(f"Initialized VerificationAgent in region {aws_region}")

    def verify_assessment(self,
                         visual_assessment: Dict,
                         social_reports: Dict,
                         official_reports: Dict) -> Dict:
        """
        Cross-verify assessment using multiple sources

        Args:
            visual_assessment: Visual damage assessment
            social_reports: Social media reports
            official_reports: Official agency reports

        Returns:
            Verification results with confidence scores
        """
        logger.info("Starting cross-verification of assessment")

        try:
            # Calculate individual confidence scores
            visual_confidence = self._calculate_visual_confidence(visual_assessment)
            social_confidence = self._calculate_social_confidence(social_reports)
            official_confidence = self._calculate_official_confidence(official_reports)

            # Cross-reference data points
            cross_reference = self._cross_reference_sources(
                visual_assessment,
                social_reports,
                official_reports
            )

            # Use AI for final verification
            ai_verification = self._ai_verification(
                visual_assessment,
                social_reports,
                official_reports,
                cross_reference
            )

            # Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(
                visual_confidence,
                social_confidence,
                official_confidence,
                cross_reference
            )

            result = {
                'overall_confidence': overall_confidence,
                'visual_confidence': visual_confidence,
                'social_confidence': social_confidence,
                'official_confidence': official_confidence,
                'cross_reference_score': cross_reference.get('agreement_score', 0.0),
                'verified_facts': cross_reference.get('verified_facts', []),
                'discrepancies': cross_reference.get('discrepancies', []),
                'ai_verification': ai_verification,
                'recommendation': self._generate_recommendation(overall_confidence)
            }

            logger.info(f"Verification complete. Overall confidence: {overall_confidence:.2f}")
            return result

        except Exception as e:
            logger.error(f"Error in verification: {str(e)}")
            return {
                'overall_confidence': 0.0,
                'error': str(e)
            }

    def _calculate_visual_confidence(self, visual_assessment: Dict) -> float:
        """Calculate confidence score for visual assessment"""
        # Base confidence on data completeness and consistency
        score = 0.5  # Base score

        if visual_assessment.get('buildings_damaged', 0) > 0:
            score += 0.15

        if visual_assessment.get('overall_severity', 0) > 0:
            score += 0.15

        if visual_assessment.get('severity_map') is not None:
            score += 0.2

        return min(score, 1.0)

    def _calculate_social_confidence(self, social_reports: Dict) -> float:
        """Calculate confidence score for social media reports"""
        # Lower base confidence due to potential misinformation
        score = 0.3

        urgent_requests = social_reports.get('urgent_requests', [])
        if len(urgent_requests) > 5:
            score += 0.2

        if social_reports.get('verified_reports', 0) > 0:
            score += 0.3

        if social_reports.get('geo_tagged_reports', 0) > 0:
            score += 0.2

        return min(score, 0.8)  # Cap social media confidence

    def _calculate_official_confidence(self, official_reports: Dict) -> float:
        """Calculate confidence score for official reports"""
        # High base confidence for official sources
        score = 0.7

        if official_reports.get('verified_by_agency'):
            score += 0.2

        if official_reports.get('on_ground_assessment'):
            score += 0.1

        return min(score, 1.0)

    def _cross_reference_sources(self,
                                 visual: Dict,
                                 social: Dict,
                                 official: Dict) -> Dict:
        """
        Cross-reference different data sources

        Args:
            visual: Visual assessment
            social: Social reports
            official: Official reports

        Returns:
            Cross-reference results
        """
        verified_facts = []
        discrepancies = []

        # Compare building damage estimates
        visual_buildings = visual.get('buildings_damaged', 0)
        official_buildings = official.get('buildings_damaged', 0)

        if official_buildings > 0:
            difference_pct = abs(visual_buildings - official_buildings) / official_buildings
            if difference_pct < 0.2:  # Within 20%
                verified_facts.append({
                    'fact': 'building_damage',
                    'visual_value': visual_buildings,
                    'official_value': official_buildings,
                    'agreement': 'high'
                })
            else:
                discrepancies.append({
                    'aspect': 'building_damage',
                    'visual_value': visual_buildings,
                    'official_value': official_buildings,
                    'difference_pct': difference_pct
                })

        # Compare severity estimates
        visual_severity = visual.get('overall_severity', 0)
        social_urgency = len(social.get('urgent_requests', []))

        if visual_severity > 7 and social_urgency > 10:
            verified_facts.append({
                'fact': 'high_severity_event',
                'visual_severity': visual_severity,
                'social_urgency': social_urgency,
                'agreement': 'high'
            })

        # Calculate agreement score
        total_comparisons = len(verified_facts) + len(discrepancies)
        agreement_score = len(verified_facts) / total_comparisons if total_comparisons > 0 else 0.5

        return {
            'verified_facts': verified_facts,
            'discrepancies': discrepancies,
            'agreement_score': agreement_score
        }

    def _ai_verification(self,
                        visual: Dict,
                        social: Dict,
                        official: Dict,
                        cross_reference: Dict) -> Dict:
        """
        Use AI for final verification and reasoning

        Args:
            visual: Visual assessment
            social: Social reports
            official: Official reports
            cross_reference: Cross-reference results

        Returns:
            AI verification results
        """
        prompt = f"""
Analyze the following disaster assessment data from multiple sources and provide verification:

VISUAL ASSESSMENT:
- Buildings Damaged: {visual.get('buildings_damaged', 0)}
- Overall Severity: {visual.get('overall_severity', 0)}/10
- Flooding: {visual.get('flooding_percentage', 0)}%

SOCIAL MEDIA REPORTS:
- Urgent Requests: {len(social.get('urgent_requests', []))}
- Trapped Persons Reported: {social.get('trapped_count', 0)}

OFFICIAL REPORTS:
- Buildings Damaged: {official.get('buildings_damaged', 0)}
- Official Severity: {official.get('severity', 'N/A')}

CROSS-REFERENCE RESULTS:
- Agreement Score: {cross_reference.get('agreement_score', 0)}
- Verified Facts: {len(cross_reference.get('verified_facts', []))}
- Discrepancies: {len(cross_reference.get('discrepancies', []))}

Please analyze:
1. Are the sources generally consistent?
2. Which sources appear most reliable for this situation?
3. Are there any red flags or concerning discrepancies?
4. What is your confidence level in the overall assessment?
5. Any recommendations for additional verification?

Provide response in JSON format:
{{
    "consistency_rating": "<high/medium/low>",
    "most_reliable_source": "<string>",
    "red_flags": [],
    "confidence_level": <0.0-1.0>,
    "recommendations": [],
    "reasoning": "<string>"
}}
"""

        try:
            response = self.bedrock_client.invoke_model(
                modelId='us.anthropic.claude-opus-4-20250514-v1:0',
                body=json.dumps({
                    'anthropic_version': 'bedrock-2023-05-31',
                    'max_tokens': 2000,
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.2
                })
            )

            result = json.loads(response['body'].read())
            content = result['content'][0]['text']

            # Parse JSON
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            logger.error(f"Error in AI verification: {str(e)}")

        return {'confidence_level': 0.5, 'reasoning': 'AI verification unavailable'}

    def _calculate_overall_confidence(self,
                                     visual_conf: float,
                                     social_conf: float,
                                     official_conf: float,
                                     cross_ref: Dict) -> float:
        """
        Calculate weighted overall confidence score

        Args:
            visual_conf: Visual confidence
            social_conf: Social media confidence
            official_conf: Official reports confidence
            cross_ref: Cross-reference results

        Returns:
            Overall confidence score (0.0-1.0)
        """
        # Weighted average with emphasis on official and visual sources
        weights = {
            'visual': 0.35,
            'official': 0.40,
            'social': 0.15,
            'cross_ref': 0.10
        }

        overall = (
            visual_conf * weights['visual'] +
            official_conf * weights['official'] +
            social_conf * weights['social'] +
            cross_ref.get('agreement_score', 0.5) * weights['cross_ref']
        )

        return round(overall, 3)

    def _generate_recommendation(self, confidence: float) -> str:
        """
        Generate recommendation based on confidence score

        Args:
            confidence: Overall confidence score

        Returns:
            Recommendation string
        """
        if confidence >= 0.8:
            return "HIGH CONFIDENCE: Proceed with response plan as assessed."
        elif confidence >= 0.6:
            return "MEDIUM CONFIDENCE: Proceed with caution, monitor for updates."
        elif confidence >= 0.4:
            return "LOW CONFIDENCE: Seek additional verification before major resource commitment."
        else:
            return "VERY LOW CONFIDENCE: Conduct on-ground assessment before proceeding."
