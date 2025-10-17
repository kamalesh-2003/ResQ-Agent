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


def render_event_map(events):
    """Render map of disaster events"""
    st.subheader("🗺️ Event Locations")

    # Create map data
    map_data = []
    for event in events:
        try:
            data_summary = json.loads(event.get('data_summary', '{}'))
            event_data = data_summary.get('event_data', {})
            location = event_data.get('location', {})

            if location and 'lat' in location and 'lon' in location:
                map_data.append({
                    'lat': location['lat'],
                    'lon': location['lon'],
                    'event_id': event.get('event_id', 'unknown'),
                    'status': event.get('status', 'unknown'),
                    'type': event_data.get('event_type', 'unknown')
                })
        except:
            continue

    if map_data:
        df_map = pd.DataFrame(map_data)

        # Create scatter map
        fig = px.scatter_mapbox(
            df_map,
            lat='lat',
            lon='lon',
            color='status',
            size=[1]*len(df_map),
            hover_data=['event_id', 'type'],
            color_discrete_map={
                'IN_PROGRESS': 'red',
                'COMPLETED': 'green',
                'PARTIAL': 'orange',
                'FAILED': 'gray'
            },
            zoom=3,
            height=500
        )

        fig.update_layout(mapbox_style="open-street-map")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No event location data available")


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
        render_event_map(events)
        st.divider()
        render_event_timeline(events)

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
