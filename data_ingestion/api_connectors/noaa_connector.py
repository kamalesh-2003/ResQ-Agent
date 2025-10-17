"""
NOAA Weather Data Connector
Fetches weather and storm event data from NOAA APIs
"""

import requests
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class NOAAWeatherConnector:
    """
    Connector for fetching weather and storm data from NOAA
    """

    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize NOAA Weather Connector

        Args:
            api_token: NOAA API token (obtain from https://www.ncdc.noaa.gov/cdo-web/token)
        """
        self.api_token = api_token
        self.base_url = "https://www.ncdc.noaa.gov/cdo-web/api/v2"
        self.storm_events_url = "https://www.ncdc.noaa.gov/stormevents/csv"

        self.session = requests.Session()
        if self.api_token:
            self.session.headers.update({'token': self.api_token})
        self.session.headers.update({
            'User-Agent': 'DisasterResponseAI/1.0',
            'Accept': 'application/json'
        })

        logger.info("Initialized NOAAWeatherConnector")

    def fetch_storm_events(self,
                          location: Dict[str, float],
                          date_range: Tuple[datetime, datetime]) -> pd.DataFrame:
        """
        Fetch NOAA Storm Events Database

        Args:
            location: {'lat': float, 'lon': float}
            date_range: Tuple of (start_date, end_date)

        Returns:
            DataFrame containing storm events
        """
        logger.info(f"Fetching storm events for location: {location}, dates: {date_range}")

        # Get location's FIPS code
        fips = self._get_fips_code(location['lat'], location['lon'])

        if not self.api_token:
            logger.warning("No API token provided, using limited public access")
            return self._fetch_storm_events_csv(date_range)

        params = {
            'datasetid': 'GHCND',
            'locationid': f'FIPS:{fips}',
            'startdate': date_range[0].strftime('%Y-%m-%d'),
            'enddate': date_range[1].strftime('%Y-%m-%d'),
            'limit': 1000,
            'includemetadata': 'true'
        }

        try:
            response = self.session.get(f"{self.base_url}/data", params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if 'results' in data:
                    df = pd.DataFrame(data['results'])
                    logger.info(f"Retrieved {len(df)} storm events")
                    return df
            else:
                logger.warning(f"API request failed with status {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching storm events: {str(e)}")

        return pd.DataFrame()

    def _fetch_storm_events_csv(self, date_range: Tuple[datetime, datetime]) -> pd.DataFrame:
        """
        Fetch storm events from CSV export (alternative method)

        Args:
            date_range: Tuple of (start_date, end_date)

        Returns:
            DataFrame with storm events
        """
        try:
            # NOAA provides CSV exports for storm events
            # This is a simplified implementation
            year = date_range[0].year
            url = f"https://www.ncdc.noaa.gov/pub/data/swdi/stormevents/csvfiles/StormEvents_details-ftp_v1.0_d{year}_c20230927.csv.gz"

            df = pd.read_csv(url, compression='gzip', low_memory=False)

            # Filter by date range
            df['BEGIN_DATE'] = pd.to_datetime(df['BEGIN_DATE'])
            mask = (df['BEGIN_DATE'] >= date_range[0]) & (df['BEGIN_DATE'] <= date_range[1])
            df = df[mask]

            logger.info(f"Retrieved {len(df)} storm events from CSV")
            return df

        except Exception as e:
            logger.error(f"Error fetching storm events CSV: {str(e)}")
            return pd.DataFrame()

    def fetch_weather_observations(self,
                                   station_id: str,
                                   date_range: Tuple[datetime, datetime]) -> pd.DataFrame:
        """
        Fetch weather observations from a specific station

        Args:
            station_id: NOAA station ID
            date_range: Tuple of (start_date, end_date)

        Returns:
            DataFrame with weather observations
        """
        logger.info(f"Fetching weather data for station: {station_id}")

        if not self.api_token:
            logger.warning("API token required for weather observations")
            return pd.DataFrame()

        params = {
            'datasetid': 'GHCND',
            'stationid': station_id,
            'startdate': date_range[0].strftime('%Y-%m-%d'),
            'enddate': date_range[1].strftime('%Y-%m-%d'),
            'limit': 1000,
            'units': 'metric'
        }

        try:
            response = self.session.get(f"{self.base_url}/data", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'results' in data:
                df = pd.DataFrame(data['results'])
                logger.info(f"Retrieved {len(df)} weather observations")
                return df
            else:
                return pd.DataFrame()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather observations: {str(e)}")
            return pd.DataFrame()

    def fetch_severe_weather_alerts(self, state: str) -> List[Dict]:
        """
        Fetch current severe weather alerts

        Args:
            state: State abbreviation

        Returns:
            List of active weather alerts
        """
        logger.info(f"Fetching weather alerts for state: {state}")

        # Use NOAA Weather API (NWS)
        alerts_url = f"https://api.weather.gov/alerts/active?area={state.upper()}"

        try:
            response = requests.get(alerts_url, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'features' in data:
                alerts = [feature['properties'] for feature in data['features']]
                logger.info(f"Retrieved {len(alerts)} active weather alerts")
                return alerts
            else:
                return []

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather alerts: {str(e)}")
            return []

    def fetch_hurricane_data(self, year: Optional[int] = None) -> pd.DataFrame:
        """
        Fetch hurricane/tropical storm data

        Args:
            year: Year to fetch data for (defaults to current year)

        Returns:
            DataFrame with hurricane data
        """
        if year is None:
            year = datetime.now().year

        logger.info(f"Fetching hurricane data for year: {year}")

        # NOAA National Hurricane Center data
        nhc_url = f"https://www.nhc.noaa.gov/data/hurdat/hurdat2-{year}.txt"

        try:
            # Hurricane data is in a special format (HURDAT2)
            response = requests.get(nhc_url, timeout=30)

            if response.status_code == 200:
                # Parse HURDAT2 format
                df = self._parse_hurdat2(response.text)
                logger.info(f"Retrieved {len(df)} hurricane records")
                return df
            else:
                logger.warning(f"Could not fetch hurricane data: status {response.status_code}")
                return pd.DataFrame()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching hurricane data: {str(e)}")
            return pd.DataFrame()

    def _get_fips_code(self, lat: float, lon: float) -> str:
        """
        Get FIPS code from latitude/longitude

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            FIPS code as string
        """
        # This is a simplified implementation
        # In production, use FCC's Census Block Conversions API or similar

        try:
            # Use FCC API for geocoding
            url = "https://geo.fcc.gov/api/census/block/find"
            params = {
                'latitude': lat,
                'longitude': lon,
                'format': 'json'
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'County' in data:
                    return data['County']['FIPS']
        except Exception as e:
            logger.warning(f"Could not get FIPS code: {str(e)}")

        return "00000"  # Default fallback

    def _parse_hurdat2(self, hurdat_text: str) -> pd.DataFrame:
        """
        Parse HURDAT2 format hurricane data

        Args:
            hurdat_text: Raw HURDAT2 text data

        Returns:
            DataFrame with parsed hurricane data
        """
        # Simplified HURDAT2 parser
        lines = hurdat_text.strip().split('\n')
        records = []

        current_storm = None
        for line in lines:
            if line.startswith('AL'):
                # Storm header line
                parts = line.split(',')
                current_storm = parts[1].strip()
            else:
                # Data line
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 7 and current_storm:
                    records.append({
                        'storm_name': current_storm,
                        'date': parts[0],
                        'time': parts[1],
                        'status': parts[2],
                        'latitude': parts[3],
                        'longitude': parts[4],
                        'max_wind': parts[5],
                        'min_pressure': parts[6]
                    })

        return pd.DataFrame(records)
