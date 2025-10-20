"""
ResQ-Agent Dashboard
Real-time disaster response monitoring and visualization
"""

import streamlit as st
import boto3
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np
from typing import Dict, List
import sys
sys.path.append('.')
from data_ingestion.api_connectors.nasa_eonet_connector import NASAEONETConnector
from data_ingestion.api_connectors.usgs_earthquake_connector import USGSEarthquakeConnector
from disaster_analysis.disaster_prioritizer import DisasterPrioritizer
from disaster_analysis.resource_allocator import ResourceAllocator
from disaster_analysis.analysis_cache import AnalysisCache

# Page config
st.set_page_config(
    page_title="ResQ-Agent Dashboard",
    page_icon="🚨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# AWS Configuration
AWS_REGION = st.secrets.get("AWS_REGION", "us-east-1")
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
s3_client = boto3.client('s3', region_name=AWS_REGION)


class DashboardData:
    """Handles data retrieval and processing for dashboard"""

    def __init__(self):
        self.events_table = dynamodb.Table('disaster-events')
        self.results_table = dynamodb.Table('assessment-results')
        self.nasa_connector = NASAEONETConnector()
        self.usgs_connector = USGSEarthquakeConnector()
        self.prioritizer = DisasterPrioritizer()
        self.allocator = ResourceAllocator()
        self.analysis_cache = AnalysisCache(cache_dir=".", cache_ttl_hours=24)

    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def get_real_nasa_disasters(_self, days=7):
        """Fetch real disasters from NASA EONET API"""
        try:
            return _self.nasa_connector.get_recent_events(days=days, status="open")
        except Exception as e:
            st.warning(f"Could not fetch NASA disasters: {str(e)}")
            return []

    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def get_usgs_earthquakes(_self, days=7, min_magnitude=4.0):
        """Fetch real earthquakes from USGS API"""
        try:
            return _self.usgs_connector.get_recent_earthquakes(days=days, min_magnitude=min_magnitude)
        except Exception as e:
            st.warning(f"Could not fetch USGS earthquakes: {str(e)}")
            return []

    def get_recent_events(self, limit=50):
        """Get recent disaster events"""
        try:
            response = self.events_table.scan(Limit=limit)
            items = response.get('Items', [])

            # Sort by timestamp
            items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            return items
        except Exception as e:
            st.error(f"Error fetching events: {str(e)}")
            return []

    def get_event_details(self, event_id):
        """Get detailed information for a specific event"""
        try:
            response = self.events_table.query(
                KeyConditionExpression='event_id = :eid',
                ExpressionAttributeValues={':eid': event_id}
            )
            items = response.get('Items', [])
            if items:
                # Get most recent entry
                items.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
                return items[0]
            return None
        except Exception as e:
            st.error(f"Error fetching event details: {str(e)}")
            return None

    def get_assessment_results(self, event_id):
        """Get assessment results for an event"""
        try:
            response = self.results_table.query(
                KeyConditionExpression='event_id = :eid',
                ExpressionAttributeValues={':eid': event_id}
            )
            return response.get('Items', [])
        except Exception as e:
            st.error(f"Error fetching assessment: {str(e)}")
            return []


def render_header():
    """Render dashboard header"""
    col1, col2, col3 = st.columns([2, 3, 1])

    with col1:
        st.title("🚨 ResQ-Agent")
        st.caption("AI-Powered Disaster Response System")

    with col2:
        st.metric("System Status", "OPERATIONAL", delta="99.9% uptime")

    with col3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()


def render_sidebar(dashboard_data):
    """Render sidebar with filters and controls"""
    st.sidebar.header("Filters & Controls")

    # Event type filter
    event_types = ["All", "Hurricane", "Earthquake", "Flood", "Fire", "Tornado"]
    selected_type = st.sidebar.selectbox("Event Type", event_types)

    # Time range filter
    time_range = st.sidebar.selectbox(
        "Time Range",
        ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "All Time"]
    )

    # Status filter
    status_filter = st.sidebar.multiselect(
        "Status",
        ["IN_PROGRESS", "COMPLETED", "PARTIAL", "FAILED"],
        default=["IN_PROGRESS", "COMPLETED"]
    )

    st.sidebar.divider()

    # Quick actions
    st.sidebar.header("Quick Actions")
    if st.sidebar.button("📊 Generate Report", use_container_width=True):
        st.sidebar.success("Report generation started")

    if st.sidebar.button("🚁 Deploy Resources", use_container_width=True):
        st.sidebar.info("Opening resource deployment interface...")

    if st.sidebar.button("⚠️ Create Alert", use_container_width=True):
        st.sidebar.warning("Alert creation form opened")

    return selected_type, time_range, status_filter


def render_metrics_overview(events):
    """Render key metrics overview"""
    st.subheader("📈 Key Metrics")

    col1, col2, col3, col4, col5 = st.columns(5)

    # Calculate metrics
    active_events = len([e for e in events if e.get('status') == 'IN_PROGRESS'])
    completed_events = len([e for e in events if e.get('status') == 'COMPLETED'])
    total_affected = sum([e.get('imagery_count', 0) for e in events])
    avg_response_time = "2.3 hrs"  # Placeholder
    confidence_avg = np.mean([float(e.get('data_summary', '{}').get('confidence', 0.5))
                              for e in events if 'data_summary' in e] or [0.5])

    with col1:
        st.metric("Active Events", active_events, delta=f"+{active_events - 5}")

    with col2:
        st.metric("Completed", completed_events, delta=f"+{completed_events}")

    with col3:
        st.metric("Images Analyzed", total_affected, delta="+120")

    with col4:
        st.metric("Avg Response Time", avg_response_time, delta="-0.5 hrs", delta_color="inverse")

    with col5:
        st.metric("Avg Confidence", f"{confidence_avg*100:.1f}%", delta="+5%")


def render_event_map(events, nasa_disasters=None, usgs_earthquakes=None, critical_disaster_analysis=None, top_7_analysis=None):
    """Render modern world map with disaster event circles

    Args:
        events: DynamoDB events
        nasa_disasters: NASA EONET disasters
        usgs_earthquakes: USGS earthquakes
        critical_disaster_analysis: Single critical disaster analysis (legacy)
        top_7_analysis: Top 7 disasters analysis with resources
    """
    st.subheader("🗺️ Global Disaster Map (NASA + USGS Real-Time Data)")

    # Fetch real NASA disasters if not provided
    if nasa_disasters is None or usgs_earthquakes is None:
        dashboard_data = DashboardData()
        if nasa_disasters is None:
            nasa_disasters = dashboard_data.get_real_nasa_disasters(days=7)
        if usgs_earthquakes is None:
            usgs_earthquakes = dashboard_data.get_usgs_earthquakes(days=7, min_magnitude=4.0)

    # Get critical disaster IDs
    critical_disaster_ids = set()
    top_7_disasters_map = {}  # Map event_id to disaster data with rank

    # Support both single critical disaster (legacy) and top 7 analysis
    if top_7_analysis:
        # Use top 7 analysis
        top_7_list = top_7_analysis.get('top_7_critical_disasters', [])
        for idx, disaster_item in enumerate(top_7_list, 1):
            disaster = disaster_item.get('disaster')
            if disaster:
                event_id = disaster.get('event_id')
                critical_disaster_ids.add(event_id)
                top_7_disasters_map[event_id] = {
                    'rank': idx,
                    'disaster': disaster,
                    'priority': disaster_item.get('priority_score', 0),
                    'urgency': disaster_item.get('urgency_level', 'UNKNOWN'),
                    'resources': disaster_item.get('resource_allocation', {})
                }
    elif critical_disaster_analysis:
        # Legacy single critical disaster
        critical_disaster = critical_disaster_analysis.get('disaster')
        if critical_disaster:
            event_id = critical_disaster.get('event_id')
            critical_disaster_ids.add(event_id)
            top_7_disasters_map[event_id] = {
                'rank': 1,
                'disaster': critical_disaster,
                'priority': critical_disaster_analysis.get('priority_analysis', {}).get('priority_score', 0),
                'urgency': critical_disaster_analysis.get('priority_analysis', {}).get('urgency_level', 'UNKNOWN'),
                'resources': critical_disaster_analysis.get('resource_allocation', {})
            }

    # Create map data from NASA disasters
    map_data = []
    for disaster in nasa_disasters:
        try:
            location = disaster.get('location', {})
            if location and 'lat' in location and 'lon' in location:
                # Check if disaster has location_info (means it's land-based)
                loc_info = disaster.get('location_info', {})
                is_land_based = loc_info.get('on_land', False) if loc_info else False

                map_data.append({
                    'lat': location['lat'],
                    'lon': location['lon'],
                    'event_id': disaster.get('event_id', 'unknown'),
                    'title': disaster.get('title', 'Unknown Event'),
                    'status': 'open' if disaster.get('status') == 'open' else 'closed',
                    'type': disaster.get('event_type', 'Unknown').title(),
                    'category': disaster.get('category', ''),
                    'radius_km': 50,  # Default radius
                    'severity': disaster.get('severity_estimate', 5.0),
                    'magnitude': disaster.get('magnitude', 'N/A'),
                    'sources': ', '.join(disaster.get('sources', [])[:3]),
                    'is_land_based': is_land_based
                })
        except Exception as e:
            continue

    # Add USGS earthquakes
    for earthquake in usgs_earthquakes:
        try:
            location = earthquake.get('location', {})
            if location and 'lat' in location and 'lon' in location:
                # Determine color/icon based on magnitude
                magnitude = earthquake.get('magnitude', 0)
                alert = earthquake.get('alert', None)

                # Check if earthquake has location_info (means it's land-based)
                loc_info = earthquake.get('location_info', {})
                is_land_based = loc_info.get('on_land', False) if loc_info else False

                map_data.append({
                    'lat': location['lat'],
                    'lon': location['lon'],
                    'event_id': earthquake.get('event_id', 'unknown'),
                    'title': earthquake.get('title', 'Unknown Earthquake'),
                    'status': 'open',  # Recent earthquakes are always "open"
                    'type': 'Earthquake',
                    'category': earthquake.get('category', 'Unknown'),
                    'radius_km': max(20, magnitude * 10),  # Scale radius by magnitude
                    'severity': earthquake.get('severity_estimate', 5.0),
                    'magnitude': f"M{magnitude:.1f}",
                    'sources': 'USGS',
                    'depth': f"{earthquake.get('depth_km', 0):.1f} km",
                    'alert': alert if alert else 'N/A',
                    'felt': earthquake.get('felt_reports', 0),
                    'data_source': 'USGS',
                    'is_land_based': is_land_based
                })
        except Exception as e:
            continue

    # Also add DynamoDB events if available
    for event in events:
        try:
            data_summary = json.loads(event.get('data_summary', '{}')) if isinstance(event.get('data_summary'), str) else event.get('data_summary', {})
            event_data = data_summary.get('event_data', {})
            location = event_data.get('location', {})

            if location and 'lat' in location and 'lon' in location:
                map_data.append({
                    'lat': location['lat'],
                    'lon': location['lon'],
                    'event_id': event.get('event_id', 'unknown'),
                    'title': event_data.get('title', event.get('event_id', 'Unknown')),
                    'status': event.get('status', 'unknown'),
                    'type': event_data.get('event_type', 'Unknown'),
                    'category': '',
                    'radius_km': event_data.get('radius_km', 50),
                    'severity': event_data.get('severity_estimate', 5.0),
                    'magnitude': 'N/A',
                    'sources': 'DynamoDB'
                })
        except Exception as e:
            continue

    # Add dummy example event in Houston, Texas if no real events
    if not map_data:
        map_data.append({
            'lat': 29.7604,
            'lon': -95.3698,
            'event_id': 'DEMO-HURRICANE-TX-001',
            'title': 'Demo Hurricane (Houston)',
            'status': 'IN_PROGRESS',
            'type': 'Hurricane',
            'category': 'Severe Storm',
            'radius_km': 120,
            'severity': 8.5,
            'magnitude': 'Category 4',
            'sources': 'Demo Data'
        })

    # Display count
    nasa_count = len(nasa_disasters)
    usgs_count = len(usgs_earthquakes)
    total_count = len(map_data)
    st.caption(f"Showing {total_count} active disasters: {nasa_count} from NASA EONET, {usgs_count} earthquakes from USGS (M4.0+)")

    # Always render the map
    if True:
        # Create figure with modern dark theme
        fig = go.Figure()

        # Add circles for each disaster event
        for event in map_data:
            # Check if this is in top 7 critical disasters
            event_id = event['event_id']
            is_critical = event_id in critical_disaster_ids
            critical_data = top_7_disasters_map.get(event_id)

            # Check if disaster has location info (land-based)
            is_land_based = event.get('is_land_based', False)

            # Determine color based on critical status and rank
            if is_critical and critical_data:
                rank = critical_data['rank']
                # Color gradient from bright red (rank 1) to orange-red (rank 7)
                # Rank 1: Pure red, Rank 7: Red-orange
                red_intensity = 255
                green_intensity = min(int((rank - 1) * 35), 100)  # Gradual increase
                color = f'rgba({red_intensity}, {green_intensity}, 0, 0.6)'
                line_color = f'rgba({red_intensity}, {green_intensity}, 0, 1.0)'
            elif is_land_based:
                # Land-based disasters (not in top 7) - lighter red
                color = 'rgba(255, 100, 100, 0.3)'
                line_color = 'rgba(255, 100, 100, 0.7)'
            elif event['status'] == 'IN_PROGRESS':
                color = 'rgba(200, 200, 200, 0.2)'  # Gray for ocean disasters
                line_color = 'rgba(200, 200, 200, 0.6)'
            elif event['status'] == 'COMPLETED':
                color = 'rgba(0, 255, 0, 0.2)'  # Green transparent
                line_color = 'rgba(0, 255, 0, 0.6)'
            elif event['status'] == 'PARTIAL':
                color = 'rgba(255, 165, 0, 0.3)'  # Orange transparent
                line_color = 'rgba(255, 165, 0, 0.8)'
            else:
                color = 'rgba(128, 128, 128, 0.2)'  # Gray transparent
                line_color = 'rgba(128, 128, 128, 0.6)'

            # Add affected area circle
            fig.add_trace(go.Scattermapbox(
                lat=[event['lat']],
                lon=[event['lon']],
                mode='markers',
                marker=dict(
                    size=event['radius_km'] / 2,  # Scale size
                    color=color,
                    opacity=0.6,
                    sizemode='diameter',
                    sizeref=1,
                    sizemin=20
                ),
                hovertemplate=(
                    f"<b>{event.get('title', event['event_id'])}</b><br>" +
                    f"Type: {event['type']}<br>" +
                    f"Category: {event.get('category', 'N/A')}<br>" +
                    f"Status: {event['status']}<br>" +
                    f"Severity: {event['severity']}/10<br>" +
                    f"Magnitude: {event.get('magnitude', 'N/A')}<br>" +
                    (f"Depth: {event.get('depth', 'N/A')}<br>" if 'depth' in event else "") +
                    (f"Alert Level: {event.get('alert', 'N/A')}<br>" if 'alert' in event else "") +
                    (f"Felt Reports: {event.get('felt', 0)}<br>" if 'felt' in event else "") +
                    f"Source: {event.get('sources', 'Unknown')}<br>" +
                    f"Location: ({event['lat']:.2f}, {event['lon']:.2f})" +
                    "<extra></extra>"
                ),
                name=event.get('title', event['event_id'])
            ))

            # Add center point marker
            fig.add_trace(go.Scattermapbox(
                lat=[event['lat']],
                lon=[event['lon']],
                mode='markers',
                marker=dict(
                    size=10,
                    color=line_color,
                    symbol='circle'
                ),
                showlegend=False,
                hoverinfo='skip'
            ))

        # Add resource allocation text boxes for all critical disasters (top 7)
        if top_7_disasters_map:
            # Sort by rank to process in order
            sorted_disasters = sorted(top_7_disasters_map.items(),
                                     key=lambda x: x[1]['rank'])

            for event_id, critical_data in sorted_disasters:
                rank = critical_data['rank']
                disaster = critical_data['disaster']
                resources = critical_data['resources']
                urgency = critical_data['urgency']

                # Find the disaster location in map_data
                disaster_location = None
                for event in map_data:
                    if event['event_id'] == event_id:
                        disaster_location = {'lat': event['lat'], 'lon': event['lon']}
                        break

                if not disaster_location or not resources:
                    continue

                helicopters = resources.get('helicopters', {})
                vehicles = resources.get('ground_vehicles', {})
                personnel = resources.get('personnel', {})

                # Calculate offset position based on rank to avoid overlap
                # Place annotations in different positions around the map
                offsets = [
                    (10, 5),   # Rank 1: Right-up
                    (-15, 5),  # Rank 2: Left-up
                    (10, -5),  # Rank 3: Right-down
                    (-15, -5), # Rank 4: Left-down
                    (0, 8),    # Rank 5: Above
                    (0, -8),   # Rank 6: Below
                    (12, 0),   # Rank 7: Far right
                ]

                offset_x, offset_y = offsets[min(rank - 1, len(offsets) - 1)]

                # Add info box for each top disaster
                fig.add_annotation(
                    x=disaster_location['lon'] + offset_x,
                    y=disaster_location['lat'] + offset_y,
                    xref='x',
                    yref='y',
                    text=(
                        f"<b>RANK #{rank} DISASTER</b><br>"
                        f"<b>{disaster.get('title', 'Unknown')[:30]}</b><br>"
                        f"━━━━━━━━━━━━━━━<br>"
                        f"🚁 Helis: {helicopters.get('total', 0)} | "
                        f"🚙 Vehicles: {vehicles.get('total', 0)}<br>"
                        f"👥 Personnel: {personnel.get('total', 0)}<br>"
                        f"⚡ {resources.get('deployment_priority', 'N/A')} | "
                        f"📊 {urgency}"
                    ),
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    arrowwidth=2,
                    arrowcolor=f'rgba(255, {min(int((rank - 1) * 35), 100)}, 0, 0.8)',
                    ax=-30,
                    ay=0,
                    align='left',
                    bgcolor='rgba(45, 55, 72, 0.92)',
                    bordercolor=f'rgba(255, {min(int((rank - 1) * 35), 100)}, 0, 1.0)',
                    borderwidth=2,
                    borderpad=8,
                    font=dict(
                        size=9,
                        color='rgba(255, 255, 255, 0.95)',
                        family='monospace'
                    ),
                    xanchor='left',
                    yanchor='middle'
                )

        # Update layout with modern dark map style
        fig.update_layout(
            mapbox=dict(
                style="carto-darkmatter",  # Modern dark theme (no token needed)
                center=dict(lat=20, lon=0),  # Center on world view
                zoom=1.5
            ),
            height=600,
            margin=dict(l=0, r=0, t=0, b=0),
            showlegend=False,
            hovermode='closest',
            paper_bgcolor='#0E1117',  # Match Streamlit dark theme
            plot_bgcolor='#0E1117'
        )

        st.plotly_chart(fig, use_container_width=True)

        # Add legend
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown("🔴 **IN PROGRESS** - Active disaster")
        with col2:
            st.markdown("🟢 **COMPLETED** - Response complete")
        with col3:
            st.markdown("🟠 **PARTIAL** - Partial response")
        with col4:
            st.markdown("⚪ **OTHER** - Inactive/Failed")


def render_event_timeline(events):
    """Render timeline of events"""
    st.subheader("📅 Event Timeline")

    # Prepare timeline data
    timeline_data = []
    for event in events[:20]:  # Last 20 events
        try:
            timestamp = event.get('timestamp', 0)
            dt = datetime.fromtimestamp(timestamp)

            timeline_data.append({
                'timestamp': dt,
                'event_id': event.get('event_id', 'unknown'),
                'status': event.get('status', 'unknown'),
                'imagery_count': event.get('imagery_count', 0)
            })
        except:
            continue

    if timeline_data:
        df_timeline = pd.DataFrame(timeline_data)
        df_timeline = df_timeline.sort_values('timestamp')

        fig = px.scatter(
            df_timeline,
            x='timestamp',
            y='imagery_count',
            color='status',
            hover_data=['event_id'],
            title="Event Activity Over Time"
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No timeline data available")


def render_agent_activity():
    """Render Bedrock Agent activity and mock reports"""
    st.subheader("🤖 AI Agent Activity")

    st.caption("Automated multi-agent system powered by AWS Bedrock")

    # Show last agent run
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Last Analysis", "2 minutes ago", delta="Auto-running every 10min")

    with col2:
        st.metric("Disasters Analyzed", "47", delta="+3 new")

    with col3:
        st.metric("Reports Generated", "12", delta="+1 today")

    st.divider()

    # Mock report notifications
    st.subheader("📊 Recent Agent Reports (Mock)")

    st.caption("Reports automatically generated and sent to emergency contacts")

    mock_reports = [
        {
            'time': '5 minutes ago',
            'disaster': 'M6.5 Earthquake - Sarmi, Indonesia',
            'recipients': ['Indonesia BNPB', 'USAID', 'UN OCHA', 'Red Cross Indonesia'],
            'status': 'Delivered',
            'priority': 'CRITICAL',
            'resources': '18 helicopters, 120 vehicles, 375 personnel'
        },
        {
            'time': '15 minutes ago',
            'disaster': 'M5.2 Earthquake - Tonga',
            'recipients': ['Tonga NEMO', 'Pacific Disaster Center', 'Red Cross Pacific'],
            'status': 'Delivered',
            'priority': 'HIGH',
            'resources': '8 helicopters, 45 vehicles, 120 personnel'
        },
        {
            'time': '25 minutes ago',
            'disaster': 'Wildfire - California, USA',
            'recipients': ['Cal Fire', 'FEMA', 'California OES'],
            'status': 'Delivered',
            'priority': 'HIGH',
            'resources': '12 helicopters, 85 vehicles, 200 personnel'
        },
        {
            'time': '35 minutes ago',
            'disaster': 'M4.8 Earthquake - Japan',
            'recipients': ['JMA', 'FDMA Japan', 'Japanese Red Cross'],
            'status': 'Delivered',
            'priority': 'MEDIUM',
            'resources': '5 helicopters, 30 vehicles, 80 personnel'
        }
    ]

    for report in mock_reports:
        with st.expander(f"📄 {report['disaster']} - {report['time']}", expanded=False):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.write(f"**Status:** ✅ {report['status']}")
                st.write(f"**Priority:** {report['priority']}")
                st.write(f"**Recipients:** {', '.join(report['recipients'])}")
                st.write(f"**Resources Allocated:** {report['resources']}")

            with col2:
                st.success("✅ PDF Report generated")
                st.success("✅ Emails sent")

            st.divider()

            # Mock report content preview
            st.markdown("**Report Summary:**")
            st.markdown(f"""
            - **Event Analysis:** AI-powered priority scoring and risk assessment
            - **Population Impact:** Geocoded location with population density analysis
            - **Resource Allocation:** Calculated based on severity, population, and disaster type
            - **Deployment Plan:** Immediate action required with {report['resources'].split(',')[0]}
            - **Contact Information:** Local emergency services and international aid organizations
            """)

            st.download_button(
                label="📥 Download Report (Mock PDF)",
                data=f"Mock PDF Report\n\nDisaster: {report['disaster']}\nPriority: {report['priority']}\nResources: {report['resources']}\n\nThis is a mock report for demonstration purposes.",
                file_name=f"disaster_report_{report['time'].replace(' ', '_').replace(':', '')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    st.divider()

    # Agent architecture info
    with st.expander("ℹ️ About the Multi-Agent System"):
        st.markdown("""
        ### AWS Bedrock Multi-Agent Architecture

        **Agent 1: Priority Analysis Agent**
        - Runs every 10 minutes via EventBridge
        - Fetches data from NASA EONET and USGS APIs
        - Analyzes location (land vs ocean)
        - Geocodes population density
        - Calculates priority scores (0-100)
        - Identifies top 3 critical disasters

        **Agent 2: Resource Allocation Agent**
        - Triggered by Agent 1 for critical disasters
        - Calculates required helicopters, vehicles, personnel
        - Determines supply needs (water, food, medical)
        - Creates deployment plan
        - Stores results in DynamoDB

        **Agent 3: Report Generation Agent** *(Mock - Not Yet Deployed)*
        - Generates PDF reports from analysis
        - Sends to country emergency contacts
        - Includes maps, data, and action plans
        - Tracks delivery status

        **Foundation Model:** Claude 3.5 Sonnet via Amazon Bedrock

        **Action Groups:** Lambda-backed APIs for data fetching, geocoding, and calculations
        """)

    st.info("💡 **Note:** Agent reports shown above are mock examples. The full multi-agent system with report generation and email delivery is ready for deployment to AWS.")


def render_top_7_disasters_analysis(dashboard_data):
    """Render top 7 critical disasters analysis with resource allocation

    Returns:
        dict: Analysis data with top_7_critical_disasters list
    """
    st.subheader("🎯 Top 7 Critical Disasters (AI Analysis)")

    # Import the top_7_analysis module
    import sys
    sys.path.append('dashboard')
    from top_7_analysis import analyze_top_7_disasters, load_top_7_analysis

    # Add button to run analysis
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("🔄 Reload", use_container_width=True):
            with st.spinner("🤖 Running Bedrock AI analysis on all disasters... (may take 1-2 minutes)"):
                result = analyze_top_7_disasters()
                if result['success']:
                    st.success("Analysis complete!")
                    return result['data']
                else:
                    st.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
                    return None

    # Try to load existing analysis
    analysis_data = load_top_7_analysis()

    if not analysis_data:
        st.info("No analysis available yet. Click 'Analyze Top 7' to run Bedrock AI analysis.")
        return None

    # Display top 7 disasters
    top_7 = analysis_data.get('top_7_critical_disasters', [])

    if not top_7:
        st.warning("No critical disasters found in analysis")
        return None

    # Show summary
    st.caption(f"Analyzed {analysis_data.get('total_disasters_analyzed', 0)} disasters total")

    # Display each of the top 7 in a compact format
    for idx, disaster_item in enumerate(top_7, 1):
        disaster = disaster_item.get('disaster', {})
        resources = disaster_item.get('resource_allocation', {})

        with st.expander(f"#{idx}: {disaster.get('title', 'Unknown')}", expanded=(idx <= 3)):
            col1, col2, col3 = st.columns(3)

            with col1:
                loc_info = disaster.get('location_info', {})
                st.write(f"**Location:** {loc_info.get('city', 'Unknown')}, {loc_info.get('country', '')}")
                st.write(f"**Urgency:** {disaster_item.get('urgency_level', 'UNKNOWN')}")
                st.write(f"**Priority Score:** {disaster_item.get('priority_score', 0)}/100")

            with col2:
                helicopters = resources.get('helicopters', {})
                vehicles = resources.get('ground_vehicles', {})
                st.write(f"**Helicopters:** {helicopters.get('total', 0)}")
                st.write(f"**Vehicles:** {vehicles.get('total', 0)}")
                st.write(f"**Deployment:** {resources.get('deployment_priority', 'N/A')}")

            with col3:
                personnel = resources.get('personnel', {})
                st.write(f"**Personnel:** {personnel.get('total', 0)}")
                st.write(f"**Severity:** {disaster.get('severity_estimate', 0)}/10")
                pop_info = disaster.get('population_info', {})
                st.write(f"**Pop. Density:** {pop_info.get('density', 'unknown').upper()}")

    return analysis_data


def render_critical_disaster_analysis(dashboard_data, force_refresh=False):
    """Render AI-powered critical disaster analysis with resource allocation

    Returns:
        dict: Analysis data containing disaster, priority_analysis, and resource_allocation
    """
    st.subheader("🎯 AI Critical Disaster Analysis")

    # Add refresh button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.write("")  # Empty space for alignment

    with col2:
        if st.button("🔄 Run New Analysis", use_container_width=True):
            force_refresh = True
            st.info("Forcing new Bedrock AI analysis...")

    try:
        # Get all disasters
        nasa_disasters = dashboard_data.get_real_nasa_disasters(days=7)
        usgs_earthquakes = dashboard_data.get_usgs_earthquakes(days=7, min_magnitude=4.0)
        all_disasters = nasa_disasters + usgs_earthquakes

        if not all_disasters:
            st.info("No active disasters found")
            return None

        # Check cache first (unless force refresh)
        cached_analysis = None
        if not force_refresh:
            cached_analysis = dashboard_data.analysis_cache.get_cached_analysis(all_disasters)

        if cached_analysis:
            # Use cached data - NO Bedrock calls
            priority_result = cached_analysis.get('priority_analysis', {})
            critical_disaster = priority_result.get('disaster')
            resources = cached_analysis.get('resource_allocation', {})

        else:
            # Run fresh analysis with Bedrock
            if force_refresh:
                dashboard_data.analysis_cache.invalidate_cache()

            with st.spinner("🤖 Analyzing disasters with Bedrock AI... (this may take 30-60 seconds)"):
                # Prioritize with AI
                priority_result = dashboard_data.prioritizer.prioritize_disasters_with_ai(all_disasters)

                if not priority_result:
                    st.warning("No land-based disasters near populated areas found")
                    return None

                critical_disaster = priority_result.get('disaster')

            # Allocate resources with AI
            with st.spinner("🤖 Calculating resource allocation with Bedrock AI... (this may take 20-40 seconds)"):
                resources = dashboard_data.allocator.allocate_resources(critical_disaster)

            # Save to cache
            analysis_data = {
                'disaster': critical_disaster,
                'priority_analysis': priority_result,
                'resource_allocation': resources
            }
            dashboard_data.analysis_cache.save_analysis(analysis_data, all_disasters)

        # Display results (same whether cached or fresh)
        loc_info = critical_disaster.get('location_info', {})
        pop_info = critical_disaster.get('population_info', {})

        # Display critical disaster
        st.success(f"**CRITICAL:** {critical_disaster.get('title')}")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Urgency Level", priority_result.get('urgency_level', 'UNKNOWN'))
            st.metric("Priority Score", f"{priority_result.get('priority_score', 0)}/100")

        with col2:
            st.metric("Location", f"{loc_info.get('city', 'Unknown')}, {loc_info.get('country', '')}")
            st.metric("Population Density", pop_info.get('density', 'unknown').upper())

        with col3:
            st.metric("Severity", f"{critical_disaster.get('severity_estimate', 0)}/10")
            st.metric("Affected Population", f"~{priority_result.get('estimated_affected_population', 0):,}")

        # AI Reasoning
        st.info(f"**AI Reasoning:** {priority_result.get('reasoning', 'N/A')}")

        st.divider()
        st.subheader("📦 AI-Generated Resource Allocation")

        # Resources breakdown
        col1, col2, col3, col4 = st.columns(4)

        helicopters = resources.get('helicopters', {})
        vehicles = resources.get('ground_vehicles', {})
        personnel = resources.get('personnel', {})
        supplies = resources.get('supplies', {})

        with col1:
            st.markdown("**🚁 HELICOPTERS**")
            st.write(f"S&R: {helicopters.get('search_and_rescue', 0)}")
            st.write(f"Medevac: {helicopters.get('medical_evacuation', 0)}")
            st.write(f"Supply: {helicopters.get('supply_delivery', 0)}")
            st.metric("Total", helicopters.get('total', 0))

        with col2:
            st.markdown("**🚙 GROUND VEHICLES**")
            st.write(f"Ambulances: {vehicles.get('ambulances', 0)}")
            st.write(f"Fire Trucks: {vehicles.get('fire_trucks', 0)}")
            st.write(f"Rescue: {vehicles.get('rescue_trucks', 0)}")
            st.metric("Total", vehicles.get('total', 0))

        with col3:
            st.markdown("**👥 PERSONNEL**")
            st.write(f"Medical: {personnel.get('medical_teams', 0)}")
            st.write(f"Rescue: {personnel.get('rescue_teams', 0)}")
            st.write(f"Fire: {personnel.get('firefighters', 0)}")
            st.metric("Total", personnel.get('total', 0))

        with col4:
            st.markdown("**📦 SUPPLIES**")
            st.write(f"Water: {supplies.get('water_liters', 0):,}L")
            st.write(f"Food: {supplies.get('food_meals', 0):,}")
            st.write(f"Tents: {supplies.get('shelter_tents', 0)}")
            st.write(f"Med Kits: {supplies.get('medical_kits', 0)}")

        # Deployment info
        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**⚡ Deployment Priority:** `{resources.get('deployment_priority', 'N/A')}`")
            st.markdown(f"**⏱️ Setup Time:** {resources.get('estimated_setup_hours', 0)} hours")
            st.markdown(f"**🏢 Command Center:** {resources.get('command_center_location', 'TBD')}")

        with col2:
            if resources.get('evacuation_zones'):
                st.markdown("**🚨 Evacuation Zones:**")
                for zone in resources['evacuation_zones']:
                    st.write(f"- {zone}")

        if resources.get('special_equipment'):
            st.markdown("**🛠️ Special Equipment:**")
            st.write(", ".join(resources['special_equipment']))

        # AI reasoning for allocation
        st.info(f"**AI Allocation Reasoning:** {resources.get('reasoning', 'N/A')}")

        # Return the analysis data for use in other components (like the map)
        return {
            'disaster': critical_disaster,
            'priority_analysis': priority_result,
            'resource_allocation': resources
        }

    except Exception as e:
        st.error(f"Error in AI analysis: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        return None


def render_event_details(dashboard_data, event_id):
    """Render detailed view of a specific event"""
    st.header(f"Event Details: {event_id}")

    # Get event data
    event = dashboard_data.get_event_details(event_id)
    if not event:
        st.error("Event not found")
        return

    # Get assessment results
    assessments = dashboard_data.get_assessment_results(event_id)

    # Parse data
    try:
        data_summary = json.loads(event.get('data_summary', '{}'))
    except:
        data_summary = {}

    # Event overview
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Overview")
        st.write(f"**Status:** {event.get('status', 'unknown')}")
        st.write(f"**Imagery:** {event.get('imagery_count', 0)} images")
        st.write(f"**Shelters:** {event.get('shelters_count', 0)} available")

    with col2:
        st.subheader("Assessment")
        if assessments:
            latest = assessments[0]
            confidence = float(latest.get('confidence_score', 0))
            st.metric("Confidence Score", f"{confidence*100:.1f}%")
            st.write(f"**Status:** {latest.get('status', 'unknown')}")

    with col3:
        st.subheader("Social Reports")
        social_count = data_summary.get('data', {}).get('social', {}).get('total_reports', 0)
        st.metric("Reports", social_count)

    st.divider()

    # Visual assessment
    st.subheader("Visual Damage Assessment")
    visual_data = data_summary.get('data', {}).get('imagery', {})

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Before Images:** {len(visual_data.get('before', []))}")
        st.write(f"**After Images:** {len(visual_data.get('after', []))}")

    with col2:
        st.write(f"**Total Images:** {visual_data.get('total_images', 0)}")

    # Emergency resources
    st.subheader("Emergency Resources")
    emergency_data = data_summary.get('data', {}).get('emergency', {})
    resources = emergency_data.get('resources', {})

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Medical Teams", resources.get('medical_teams', 0))
    with col2:
        st.metric("Rescue Teams", resources.get('rescue_teams', 0))
    with col3:
        st.metric("Helicopters", resources.get('helicopters', 0))
    with col4:
        st.metric("Supplies (tons)", resources.get('supplies_tons', 0))


def render_event_list(events):
    """Render list of events"""
    st.subheader("📋 Recent Events")

    # Create dataframe
    event_list = []
    for event in events[:20]:
        try:
            timestamp = datetime.fromtimestamp(event.get('timestamp', 0))
            event_list.append({
                'Event ID': event.get('event_id', 'unknown'),
                'Time': timestamp.strftime('%Y-%m-%d %H:%M'),
                'Status': event.get('status', 'unknown'),
                'Images': event.get('imagery_count', 0),
                'Shelters': event.get('shelters_count', 0),
                'Reports': event.get('social_reports_count', 0)
            })
        except:
            continue

    if event_list:
        df_events = pd.DataFrame(event_list)

        # Style dataframe
        def highlight_status(row):
            if row['Status'] == 'COMPLETED':
                return ['background-color: #90EE90'] * len(row)
            elif row['Status'] == 'IN_PROGRESS':
                return ['background-color: #FFD700'] * len(row)
            elif row['Status'] == 'FAILED':
                return ['background-color: #FFB6C1'] * len(row)
            return [''] * len(row)

        st.dataframe(
            df_events.style.apply(highlight_status, axis=1),
            use_container_width=True,
            hide_index=True
        )

        # Event selection
        selected_event = st.selectbox("View Details", df_events['Event ID'].tolist())
        if selected_event:
            render_event_details(DashboardData(), selected_event)
    else:
        st.info("No events available")


def main():
    """Main dashboard function"""
    # Initialize data handler
    dashboard_data = DashboardData()

    # Render header
    render_header()

    # Render sidebar
    selected_type, time_range, status_filter = render_sidebar(dashboard_data)

    # Get events
    events = dashboard_data.get_recent_events(limit=100)

    # Filter events
    if status_filter:
        events = [e for e in events if e.get('status') in status_filter]

    # Main content
    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Events", "Analytics", "Settings"])

    with tab1:
        render_metrics_overview(events)
        st.divider()

        # Get top 7 disasters analysis
        top_7_analysis = render_top_7_disasters_analysis(dashboard_data)
        st.divider()

        # Render map with top 7 disasters overlay
        render_event_map(events, top_7_analysis=top_7_analysis)
        st.divider()
        render_event_timeline(events)
        st.divider()

        # Render agent activity (mock reports)
        render_agent_activity()

    with tab2:
        render_event_list(events)

    with tab3:
        st.subheader("📊 Analytics & Insights")
        st.info("Analytics dashboard coming soon")

        # Placeholder charts
        col1, col2 = st.columns(2)
        with col1:
            st.line_chart(np.random.randn(30, 3))
        with col2:
            st.bar_chart(np.random.randn(30, 3))

    with tab4:
        st.subheader("⚙️ Settings")
        st.info("Settings panel coming soon")

        # API Configuration
        with st.expander("API Configuration"):
            st.text_input("AWS Region", value="us-east-1")
            st.text_input("S3 Bucket", value="resq-agent-data-lake")
            st.text_input("Bedrock Knowledge Base ID", value="")

        # Notification Settings
        with st.expander("Notifications"):
            st.checkbox("Email Alerts", value=True)
            st.checkbox("SMS Alerts", value=False)
            st.checkbox("Push Notifications", value=True)


if __name__ == "__main__":
    main()

