"""
FEMA Data Connector
Fetches disaster declarations, public assistance data, and shelter information from FEMA API
"""

import requests
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FEMADataConnector:
    """
    Connector for fetching data from FEMA's OpenFEMA API
    """

    def __init__(self, api_version: str = "v2"):
        """
        Initialize FEMA Data Connector

        Args:
            api_version: FEMA API version to use
        """
        self.base_url = f"https://www.fema.gov/api/open/{api_version}"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'DisasterResponseAI/1.0',
            'Accept': 'application/json'
        })

        logger.info(f"Initialized FEMADataConnector with API version: {api_version}")

    def fetch_disaster_declarations(self,
                                    state: Optional[str] = None,
                                    incident_type: Optional[str] = None,
                                    limit: int = 100) -> pd.DataFrame:
        """
        Fetch FEMA disaster declarations

        Args:
            state: State abbreviation (e.g., 'CA', 'FL')
            incident_type: Type of incident (e.g., 'Hurricane', 'Flood', 'Fire')
            limit: Maximum number of results

        Returns:
            DataFrame containing disaster declarations
        """
        logger.info(f"Fetching disaster declarations for state: {state}, type: {incident_type}")

        endpoint = f"{self.base_url}/DisasterDeclarationsSummaries"
        params = {
            'declarationType': 'DR',  # Major Disaster
            '$top': limit,
            '$orderby': 'declarationDate desc'
        }

        if state:
            params['state'] = state.upper()

        if incident_type:
            params['incidentType'] = incident_type

        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'DisasterDeclarationsSummaries' in data:
                df = pd.DataFrame(data['DisasterDeclarationsSummaries'])
                logger.info(f"Retrieved {len(df)} disaster declarations")
                return df
            else:
                logger.warning("No disaster declarations found in response")
                return pd.DataFrame()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching disaster declarations: {str(e)}")
            return pd.DataFrame()

    def fetch_public_assistance_data(self, disaster_number: int) -> Dict:
        """
        Fetch FEMA Public Assistance project data

        Args:
            disaster_number: FEMA disaster declaration number

        Returns:
            Dictionary containing public assistance data
        """
        logger.info(f"Fetching public assistance data for disaster: {disaster_number}")

        endpoint = f"{self.base_url}/PublicAssistanceApplicants"
        params = {
            'disasterNumber': disaster_number,
            '$top': 1000
        }

        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            logger.info(f"Retrieved public assistance data for disaster {disaster_number}")
            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching public assistance data: {str(e)}")
            return {}

    def fetch_shelter_data(self, state: str) -> List[Dict]:
        """
        Fetch National Shelter System data

        Args:
            state: State abbreviation

        Returns:
            List of shelter information dictionaries
        """
        logger.info(f"Fetching shelter data for state: {state}")

        endpoint = f"{self.base_url}/FemaRegions"

        # Note: Actual shelter API endpoint may vary
        # This is a simplified implementation
        params = {
            'state': state.upper(),
            '$top': 500
        }

        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Extract shelter information if available
            shelters = []
            if isinstance(data, dict) and 'shelters' in data:
                shelters = data['shelters']

            logger.info(f"Retrieved {len(shelters)} shelters for state {state}")
            return shelters

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching shelter data: {str(e)}")
            return []

    def fetch_disaster_by_id(self, disaster_id: str) -> Optional[Dict]:
        """
        Fetch details for a specific disaster by ID

        Args:
            disaster_id: FEMA disaster ID

        Returns:
            Dictionary with disaster details or None
        """
        logger.info(f"Fetching disaster details for ID: {disaster_id}")

        endpoint = f"{self.base_url}/DisasterDeclarationsSummaries"
        params = {
            'disasterNumber': disaster_id,
            '$top': 1
        }

        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'DisasterDeclarationsSummaries' in data and data['DisasterDeclarationsSummaries']:
                return data['DisasterDeclarationsSummaries'][0]
            else:
                logger.warning(f"No disaster found with ID: {disaster_id}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching disaster by ID: {str(e)}")
            return None

    def fetch_individual_assistance_data(self, disaster_number: int) -> pd.DataFrame:
        """
        Fetch Individual Assistance program data

        Args:
            disaster_number: FEMA disaster number

        Returns:
            DataFrame with individual assistance data
        """
        logger.info(f"Fetching individual assistance data for disaster: {disaster_number}")

        endpoint = f"{self.base_url}/IndividualAssistanceApprovedIhpAmount"
        params = {
            'disasterNumber': disaster_number,
            '$top': 10000
        }

        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # Extract data array from response
            records = []
            if isinstance(data, dict):
                for key in data.keys():
                    if isinstance(data[key], list):
                        records = data[key]
                        break

            df = pd.DataFrame(records)
            logger.info(f"Retrieved {len(df)} individual assistance records")
            return df

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching individual assistance data: {str(e)}")
            return pd.DataFrame()

    def get_recent_disasters(self, days: int = 30, limit: int = 50) -> pd.DataFrame:
        """
        Get recent disaster declarations within specified days

        Args:
            days: Number of days to look back
            limit: Maximum number of results

        Returns:
            DataFrame with recent disasters
        """
        from_date = (datetime.now() - pd.Timedelta(days=days)).strftime('%Y-%m-%d')

        logger.info(f"Fetching disasters since {from_date}")

        endpoint = f"{self.base_url}/DisasterDeclarationsSummaries"
        params = {
            '$filter': f"declarationDate ge '{from_date}'",
            '$top': limit,
            '$orderby': 'declarationDate desc'
        }

        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'DisasterDeclarationsSummaries' in data:
                df = pd.DataFrame(data['DisasterDeclarationsSummaries'])
                logger.info(f"Retrieved {len(df)} recent disasters")
                return df
            else:
                return pd.DataFrame()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching recent disasters: {str(e)}")
            return pd.DataFrame()
