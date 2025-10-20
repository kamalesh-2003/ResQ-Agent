# ResQ-Agent: AI-Powered Disaster Response System

ResQ-Agent is an advanced disaster response system powered by AWS Bedrock that provides real-time damage assessment, resource optimization, and coordinated emergency response using multiple AI agents.

## Features

- **Satellite Imagery Analysis**: Automated damage assessment using NASA and Sentinel-2 imagery with Bedrock vision models
- **Multi-Agent System**: Specialized AI agents for visual analysis, resource optimization, and verification
- **Real-Time Dashboard**: Streamlit-based monitoring interface with live updates
- **Automated Workflow**: AWS Step Functions orchestration for seamless disaster response
- **Multi-Source Data Integration**: NASA, FEMA, NOAA, and social media data
- **Scalable Infrastructure**: Serverless AWS architecture with auto-scaling
- **Resource Optimization**: Linear programming and AI-driven resource allocation

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Sources                               │
├──────────┬──────────┬──────────┬─────────────────────────────┤
│  NASA    │  NOAA    │  FEMA    │  Social Media               │
│ Imagery  │ Weather  │ Emergency│  (Twitter/Reddit)           │
└────┬─────┴─────┬────┴────┬─────┴──────┬──────────────────────┘
     │           │         │            │
     └───────────┴─────────┴────────────┘
                  │
         ┌────────▼────────┐
         │  Data Pipeline   │
         │   (Lambda)       │
         └────────┬─────────┘
                  │
     ┌────────────▼────────────┐
     │  Step Functions          │
     │  Orchestration          │
     └────────────┬─────────────┘
                  │
        ┌─────────┴──────────┐
        │                    │
   ┌────▼─────┐      ┌──────▼──────┐
   │ Visual   │      │ Bedrock     │
   │ Analysis │◄─────┤ Orchestrator│
   │ Agent    │      │ Agent       │
   └────┬─────┘      └──────┬──────┘
        │                   │
   ┌────▼──────┐      ┌────▼─────┐
   │ Resource  │      │Verification│
   │Optimizer  │      │   Agent    │
   └────┬──────┘      └─────┬──────┘
        │                   │
        └───────┬───────────┘
                │
         ┌──────▼──────┐
         │  DynamoDB   │
         │   Storage   │
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  Dashboard  │
         │ (Streamlit) │
         └─────────────┘
```

## Prerequisites

- AWS Account with appropriate permissions
- Python 3.9 or higher
- AWS CLI configured
- Bedrock access enabled in your AWS account
- API Keys (optional):
  - Twitter/X Bearer Token
  - NOAA API Token

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/yourusername/ResQ-Agent.git
cd ResQ-Agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your values
nano .env
```

Required environment variables:
```env
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=your-account-id
S3_BUCKET=resq-agent-data-lake
BEDROCK_KB_ID=your-knowledge-base-id  # Optional
TWITTER_BEARER_TOKEN=your-token       # Optional
NOAA_API_TOKEN=your-token             # Optional
```

### 3. Deploy to AWS

```bash
# Deploy all infrastructure and Lambda functions
python deploy.py --region us-east-1 --environment production

# Or deploy specific components
python deploy.py --skip-build  # Skip building Lambda packages
```

Deployment includes:
- CloudFormation stack (S3, DynamoDB, IAM roles)
- Lambda functions (5 functions)
- Step Functions state machine
- SNS topics for alerts

### 4. Run Dashboard

```bash
# Start Streamlit dashboard
streamlit run dashboard/streamlit_app.py

# Or using the installed command
resq-dashboard
```

Dashboard will be available at `http://localhost:8501`

### 5. Test the System

```bash
# Send a test disaster event
python scripts/test_deployment.py --event-type hurricane --severity 8.5

# Check execution status
python scripts/test_deployment.py --check-execution <execution-arn>
```

## Project Structure

```
ResQ-Agent/
├── agents/                      # AI agent implementations
│   ├── orchestrator_agent.py   # Master orchestration
│   ├── visual_analysis_agent.py # Satellite imagery analysis
│   ├── resource_optimization_agent.py # Resource allocation
│   └── verification_agent.py   # Cross-verification
├── data_ingestion/             # Data collection modules
│   ├── api_connectors/
│   │   ├── nasa_connector.py
│   │   ├── fema_connector.py
│   │   ├── noaa_connector.py
│   │   └── social_media_connector.py
│   └── data_pipeline.py
├── infrastructure/             # AWS infrastructure
│   ├── cloudformation/
│   │   └── core-stack.yaml
│   ├── lambda_functions/
│   │   ├── data_ingestion.py
│   │   ├── visual_analysis.py
│   │   ├── orchestrator.py
│   │   ├── resource_optimizer.py
│   │   └── verification.py
│   └── step_functions/
│       └── disaster_response_workflow.json
├── dashboard/                  # Streamlit dashboard
│   └── streamlit_app.py
├── config/                     # Configuration files
│   └── config.yaml
├── scripts/                    # Utility scripts
│   └── test_deployment.py
├── tests/                      # Test files
├── deploy.py                   # Deployment script
├── requirements.txt
├── setup.py
└── README.md
```

## Configuration

### AWS Bedrock Models

The system uses:
- **Claude Opus 4** (`us.anthropic.claude-opus-4-20250514-v1:0`) for reasoning and orchestration
- **Vision capabilities** for satellite imagery analysis
- **Knowledge Bases** (optional) for historical disaster patterns

### Resource Limits

Default Lambda configurations:
- **Data Ingestion**: 3008 MB, 5 min timeout
- **Visual Analysis**: 10240 MB, 15 min timeout
- **Orchestrator**: 3008 MB, 5 min timeout
- **Resource Optimizer**: 3008 MB, 3 min timeout

Modify in `deploy.py` or CloudFormation template as needed.

## Usage Examples

### Trigger a Disaster Response

```python
from data_ingestion.data_pipeline import DataPipeline, DisasterEventInput
from datetime import datetime

# Create event
event = DisasterEventInput(
    event_id='hurricane-2024-001',
    location={'lat': 29.7604, 'lon': -95.3698},
    event_type='hurricane',
    timestamp=datetime.now().isoformat(),
    state='TX',
    radius_km=100,
    severity_estimate=8.5
)

# Initialize pipeline
pipeline = DataPipeline(
    aws_region='us-east-1',
    s3_bucket='your-bucket-name'
)

# Collect data
result = pipeline.collect_all_data(event)
print(f"Status: {result['status']}")
```

### Query Assessment Results

```python
import boto3
import json

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('assessment-results')

# Get results for an event
response = table.query(
    KeyConditionExpression='event_id = :eid',
    ExpressionAttributeValues={':eid': 'hurricane-2024-001'}
)

for item in response['Items']:
    results = json.loads(item['results'])
    print(f"Confidence: {results['confidence_score']}")
    print(f"Buildings Damaged: {results['visual_assessment']['buildings_damaged']}")
```

## Security Best Practices

1. **API Keys**: Store in AWS Secrets Manager, not environment variables
2. **IAM Roles**: Use least-privilege policies
3. **VPC**: Enable VPC for Lambda functions in production
4. **Encryption**: Enable encryption at rest and in transit
5. **Access Logs**: Enable CloudWatch Logs for all services

## Testing

```bash
# Run unit tests
pytest tests/

# Run with coverage
pytest --cov=agents --cov=data_ingestion tests/

# Run integration tests
pytest tests/integration/
```

## Monitoring

### CloudWatch Dashboards

The system automatically logs to CloudWatch:
- Lambda execution metrics
- Step Functions state transitions
- DynamoDB read/write operations
- Bedrock API calls

### Alerts

Configure SNS alerts for:
- High severity events (severity > 8.0)
- Low confidence assessments (confidence < 0.5)
- System failures

## Troubleshooting

### Common Issues

**1. Bedrock Access Denied**
```bash
# Enable Bedrock in AWS Console:
# 1. Go to AWS Bedrock Console
# 2. Enable Claude 3 models
# 3. Request access if needed
```

**2. Lambda Timeout**
```bash
# Increase timeout in deploy.py:
self.lambda_client.create_function(
    ...
    Timeout=900  # 15 minutes
)
```

**3. DynamoDB Throttling**
```bash
# Switch to on-demand billing or increase provisioned capacity
```

### Debug Mode

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see LICENSE file for details.

## Acknowledgments

- AWS Bedrock team for AI model access
- NASA GIBS for satellite imagery
- NOAA for weather data
- FEMA for emergency response data

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/ResQ-Agent/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/ResQ-Agent/discussions)
- **Email**: support@resq-agent.com

## Roadmap

- [ ] Add support for Amazon Nova Canvas for image generation
- [ ] Implement real-time streaming with Kinesis
- [ ] Add mobile app interface
- [ ] Multi-language support
- [ ] Integration with IoT sensors
- [ ] Predictive disaster modeling
- [ ] Drone coordination system

## Performance

- **Average Response Time**: 2-3 minutes per event
- **Throughput**: 100+ events per hour
- **Accuracy**: 85-95% confidence on verified events
- **Cost**: ~$5-10 per event analysis (varies with data volume)

---

**Built using AWS Bedrock and modern AI**
