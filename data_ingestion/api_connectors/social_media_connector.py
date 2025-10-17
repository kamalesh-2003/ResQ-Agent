"""
Social Media Data Connector
Fetches disaster-related reports from Twitter/X and other social media platforms
"""

import requests
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import logging
import json

logger = logging.getLogger(__name__)


class SocialMediaConnector:
    """
    Connector for fetching disaster-related social media data
    """

    def __init__(self, twitter_bearer_token: Optional[str] = None):
        """
        Initialize Social Media Connector

        Args:
            twitter_bearer_token: Twitter/X API Bearer Token
        """
        self.twitter_bearer_token = twitter_bearer_token
        self.twitter_api_base = "https://api.twitter.com/2"

        self.session = requests.Session()
        if self.twitter_bearer_token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.twitter_bearer_token}',
                'User-Agent': 'DisasterResponseAI/1.0'
            })

        logger.info("Initialized SocialMediaConnector")

    def fetch_disaster_tweets(self,
                              location: Dict[str, float],
                              keywords: List[str],
                              radius_km: float = 50,
                              max_results: int = 100) -> pd.DataFrame:
        """
        Fetch disaster-related tweets from a location

        Args:
            location: {'lat': float, 'lon': float}
            keywords: List of keywords to search for
            radius_km: Search radius in kilometers
            max_results: Maximum number of tweets to fetch

        Returns:
            DataFrame containing tweets with location, text, metrics
        """
        logger.info(f"Fetching tweets for location: {location}, keywords: {keywords}")

        if not self.twitter_bearer_token:
            logger.warning("No Twitter bearer token provided, returning mock data")
            return self._generate_mock_tweets(location, keywords)

        # Build search query
        query = self._build_twitter_query(keywords, location, radius_km)

        endpoint = f"{self.twitter_api_base}/tweets/search/recent"
        params = {
            'query': query,
            'max_results': min(max_results, 100),
            'tweet.fields': 'created_at,author_id,geo,public_metrics,entities',
            'expansions': 'geo.place_id,author_id',
            'place.fields': 'full_name,geo,place_type'
        }

        try:
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if 'data' in data:
                df = pd.DataFrame(data['data'])

                # Add includes data
                if 'includes' in data:
                    df = self._enrich_tweet_data(df, data['includes'])

                logger.info(f"Retrieved {len(df)} tweets")
                return df
            else:
                logger.warning("No tweets found in response")
                return pd.DataFrame()

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching tweets: {str(e)}")
            return pd.DataFrame()

    def analyze_social_reports(self, tweets_df: pd.DataFrame) -> Dict:
        """
        Analyze social media reports for disaster intelligence

        Args:
            tweets_df: DataFrame of tweets

        Returns:
            Analysis results with urgent requests, trapped persons, etc.
        """
        if tweets_df.empty:
            return {
                'urgent_requests': [],
                'trapped_count': 0,
                'medical_emergencies': 0,
                'shelter_requests': 0,
                'verified_reports': 0,
                'geo_tagged_reports': 0,
                'sentiment_score': 0.0,
                'key_locations': []
            }

        analysis = {
            'urgent_requests': [],
            'trapped_count': 0,
            'medical_emergencies': 0,
            'shelter_requests': 0,
            'verified_reports': 0,
            'geo_tagged_reports': 0,
            'sentiment_score': 0.0,
            'key_locations': []
        }

        # Keywords for different categories
        urgent_keywords = ['trapped', 'help', 'emergency', 'urgent', 'rescue', 'sos']
        medical_keywords = ['injured', 'medical', 'ambulance', 'doctor', 'hospital']
        shelter_keywords = ['shelter', 'homeless', 'evacuate', 'evacuation']

        for idx, row in tweets_df.iterrows():
            text = row.get('text', '').lower()

            # Check for urgent requests
            if any(keyword in text for keyword in urgent_keywords):
                analysis['urgent_requests'].append({
                    'tweet_id': row.get('id'),
                    'text': row.get('text'),
                    'created_at': row.get('created_at'),
                    'location': row.get('geo', {}),
                    'priority': self._calculate_priority(text)
                })

                if 'trapped' in text:
                    analysis['trapped_count'] += 1

            # Check for medical emergencies
            if any(keyword in text for keyword in medical_keywords):
                analysis['medical_emergencies'] += 1

            # Check for shelter requests
            if any(keyword in text for keyword in shelter_keywords):
                analysis['shelter_requests'] += 1

            # Check if verified account
            if row.get('author_verified', False):
                analysis['verified_reports'] += 1

            # Check if geo-tagged
            if row.get('geo') or row.get('place_id'):
                analysis['geo_tagged_reports'] += 1

                # Extract location
                if row.get('geo'):
                    analysis['key_locations'].append(row.get('geo'))

        # Sort urgent requests by priority
        analysis['urgent_requests'].sort(key=lambda x: x['priority'], reverse=True)

        # Calculate overall sentiment (simplified)
        analysis['sentiment_score'] = self._calculate_sentiment(tweets_df)

        logger.info(f"Social media analysis complete: {analysis['trapped_count']} trapped, "
                   f"{analysis['medical_emergencies']} medical emergencies")

        return analysis

    def fetch_reddit_posts(self, subreddits: List[str], keywords: List[str]) -> pd.DataFrame:
        """
        Fetch disaster-related Reddit posts

        Args:
            subreddits: List of subreddit names
            keywords: Keywords to search for

        Returns:
            DataFrame with Reddit posts
        """
        logger.info(f"Fetching Reddit posts from {subreddits}")

        # Reddit API would require authentication
        # This is a placeholder implementation
        posts = []

        for subreddit in subreddits:
            try:
                # Use pushshift.io or Reddit API
                url = f"https://www.reddit.com/r/{subreddit}/search.json"
                params = {
                    'q': ' OR '.join(keywords),
                    'limit': 100,
                    'sort': 'new'
                }

                response = requests.get(url, params=params,
                                       headers={'User-Agent': 'DisasterResponseAI/1.0'},
                                       timeout=30)

                if response.status_code == 200:
                    data = response.json()
                    if 'data' in data and 'children' in data['data']:
                        for post in data['data']['children']:
                            posts.append(post['data'])

            except Exception as e:
                logger.error(f"Error fetching from r/{subreddit}: {str(e)}")
                continue

        df = pd.DataFrame(posts)
        logger.info(f"Retrieved {len(df)} Reddit posts")
        return df

    def _build_twitter_query(self, keywords: List[str], location: Dict, radius_km: float) -> str:
        """Build Twitter API search query"""
        # Combine keywords with OR
        keyword_query = ' OR '.join(keywords)

        # Add location filter (point_radius)
        lat = location['lat']
        lon = location['lon']
        query = f"({keyword_query}) point_radius:[{lon} {lat} {radius_km}km]"

        # Exclude retweets for cleaner data
        query += " -is:retweet"

        return query

    def _enrich_tweet_data(self, df: pd.DataFrame, includes: Dict) -> pd.DataFrame:
        """Enrich tweet dataframe with includes data"""
        # Add place information
        if 'places' in includes:
            places_dict = {place['id']: place for place in includes['places']}
            df['place_info'] = df.get('geo', {}).apply(
                lambda x: places_dict.get(x.get('place_id')) if isinstance(x, dict) else None
            )

        # Add user information
        if 'users' in includes:
            users_dict = {user['id']: user for user in includes['users']}
            df['author_verified'] = df['author_id'].apply(
                lambda x: users_dict.get(x, {}).get('verified', False)
            )

        return df

    def _calculate_priority(self, text: str) -> int:
        """Calculate priority score for a report"""
        priority = 0

        high_priority_words = ['trapped', 'dying', 'critical', 'emergency', 'urgent']
        medium_priority_words = ['help', 'injured', 'stuck', 'rescue']

        text_lower = text.lower()

        for word in high_priority_words:
            if word in text_lower:
                priority += 10

        for word in medium_priority_words:
            if word in text_lower:
                priority += 5

        # Boost priority if numbers mentioned (people trapped)
        import re
        numbers = re.findall(r'\d+', text)
        if numbers:
            priority += 3

        return priority

    def _calculate_sentiment(self, df: pd.DataFrame) -> float:
        """Calculate overall sentiment score (simplified)"""
        if df.empty or 'text' not in df.columns:
            return 0.0

        # Simple keyword-based sentiment
        negative_words = ['dead', 'dying', 'destroyed', 'terrible', 'devastated', 'collapsed']
        positive_words = ['safe', 'rescued', 'helped', 'survived', 'recovering']

        sentiment_scores = []

        for text in df['text']:
            if not isinstance(text, str):
                continue

            text_lower = text.lower()
            score = 0

            for word in negative_words:
                if word in text_lower:
                    score -= 1

            for word in positive_words:
                if word in text_lower:
                    score += 1

            sentiment_scores.append(score)

        if sentiment_scores:
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
            # Normalize to 0-1 scale
            return max(0, min(1, (avg_sentiment + 5) / 10))

        return 0.5

    def _generate_mock_tweets(self, location: Dict, keywords: List[str]) -> pd.DataFrame:
        """Generate mock tweet data for testing"""
        mock_data = [
            {
                'id': f'tweet_{i}',
                'text': f'Mock disaster report for {keywords[0] if keywords else "event"}',
                'created_at': (datetime.now() - timedelta(hours=i)).isoformat(),
                'author_id': f'user_{i}',
                'geo': {'lat': location['lat'], 'lon': location['lon']},
                'public_metrics': {
                    'retweet_count': i * 10,
                    'like_count': i * 20
                }
            }
            for i in range(10)
        ]

        return pd.DataFrame(mock_data)

    def get_disaster_keywords(self, event_type: str) -> List[str]:
        """
        Get relevant keywords for a disaster type

        Args:
            event_type: Type of disaster (hurricane, earthquake, flood, etc.)

        Returns:
            List of relevant keywords
        """
        keyword_map = {
            'hurricane': ['hurricane', 'storm', 'flooding', 'evacuation', 'wind damage', 'power outage'],
            'earthquake': ['earthquake', 'aftershock', 'building collapse', 'trapped', 'rescue'],
            'flood': ['flood', 'flooding', 'water rising', 'stranded', 'evacuation', 'rescue'],
            'fire': ['wildfire', 'fire', 'evacuation', 'smoke', 'burning', 'flames'],
            'tornado': ['tornado', 'twister', 'shelter', 'damage', 'destroyed'],
            'tsunami': ['tsunami', 'wave', 'coastal flooding', 'evacuation', 'warning'],
        }

        # Default keywords for any disaster
        default_keywords = ['disaster', 'emergency', 'help needed', 'rescue', 'trapped', 'injured']

        event_type_lower = event_type.lower()

        for disaster_type, keywords in keyword_map.items():
            if disaster_type in event_type_lower:
                return keywords + default_keywords

        return default_keywords
