# ResQ-Agent: AI-Powered Disaster Response System

ResQ-Agent is an advanced disaster response system powered by AWS Bedrock that provides real-time damage assessment, resource optimization, and coordinated emergency response using multiple AI agents.

## Features

- **Satellite Imagery Analysis**: Automated damage assessment using NASA and Sentinel-2 imagery with Bedrock vision models
- **Multi-Agent System**: Specialized AI agents for visual analysis, resource optimization, and verification
- **Real-Time Dashboard**: Streamlit-based monitoring interface with live updates
- **Automated Workflow**: AWS Step Functions orchestration for seamless disaster response
- **Multi-Source Data Integration**: NASA, FEMA, NOAA
- **Scalable Infrastructure**: Serverless AWS architecture with auto-scaling
- **Resource Optimization**: AI-driven resource allocation

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Data Sources                               │
├──────────┬──────────┬──────────┬─────────────────────────────┤
│  NASA    │  NOAA    │  FEMA    │  USGS api                   │
│ Imagery  │ Weather  │ Emergency│                             │
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

## 📋 Prerequisites

- AWS Account with appropriate permissions
- Python 3.9 or higher
- AWS CLI configured
- Bedrock access enabled in your AWS account
- API Keys (optional):
  - NOAA API Token

## 🚀 Quick Start

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

## 📦 Project Structure

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

## 🔧 Configuration

### AWS Bedrock Models

The system uses:
- **Claude 3 Sonnet** (`anthropic.claude-3-sonnet-20240229-v1:0`) for reasoning and orchestration
- **Vision capabilities** for satellite imagery analysis
- **Knowledge Bases** (optional) for historical disaster patterns

### Resource Limits

Default Lambda configurations:
- **Data Ingestion**: 3008 MB, 5 min timeout
- **Visual Analysis**: 10240 MB, 15 min timeout
- **Orchestrator**: 3008 MB, 5 min timeout
- **Resource Optimizer**: 3008 MB, 3 min timeout

Modify in `deploy.py` or CloudFormation template as needed.

## 📊 Usage Examples

## 📄 License

This project is licensed under the MIT License - see LICENSE file for details.


