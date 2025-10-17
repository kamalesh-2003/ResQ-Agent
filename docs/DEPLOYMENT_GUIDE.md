# ResQ-Agent Deployment Guide

Complete guide for deploying ResQ-Agent to AWS.

## Prerequisites Checklist

- [ ] AWS Account with admin access
- [ ] AWS CLI installed and configured
- [ ] Python 3.9+ installed
- [ ] Git installed
- [ ] Bedrock access enabled
- [ ] (Optional) API tokens for Twitter and NOAA

## Step-by-Step Deployment

### 1. Prepare AWS Account

#### Enable Bedrock Models

1. Go to AWS Bedrock Console
2. Navigate to Model Access
3. Enable the following models:
   - Anthropic Claude 3 Sonnet
   - (Optional) Amazon Nova Canvas
4. Wait for access approval (usually instant)

#### Create S3 Bucket (Optional - auto-created by CloudFormation)

```bash
aws s3 mb s3://resq-agent-data-lake-$(aws sts get-caller-identity --query Account --output text) --region us-east-1
```

### 2. Clone and Configure

```bash
# Clone repository
git clone https://github.com/yourusername/ResQ-Agent.git
cd ResQ-Agent

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
# Copy example file
cp .env.example .env
```

Edit `.env`:
```env
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012  # Your AWS account ID
S3_BUCKET=resq-agent-data-lake-123456789012

# Optional: API Tokens
TWITTER_BEARER_TOKEN=your_token_here
NOAA_API_TOKEN=your_token_here
```

### 4. Deploy Infrastructure

```bash
# Full deployment
python deploy.py --region us-east-1 --environment production
```

This will:
1. ✅ Create CloudFormation stack (5-10 minutes)
2. ✅ Build Lambda deployment packages
3. ✅ Deploy 5 Lambda functions
4. ✅ Create Step Functions state machine
5. ✅ Set up DynamoDB tables
6. ✅ Configure SNS topics

**Expected Output:**
```
========== ResQ-Agent Deployment ==========

--- Deploying CloudFormation Stack ---
Deploying stack: resq-agent-stack-production
✅ Deploying CloudFormation Stack completed successfully

--- Building Lambda Packages ---
Installing dependencies...
✅ Building Lambda Packages completed successfully

--- Deploying Lambda Functions ---
Deploying resq-data-ingestion...
✅ Deploying Lambda Functions completed successfully

--- Deploying Step Functions ---
Creating state machine: resq-disaster-response-production
✅ Deploying Step Functions completed successfully

--- Verifying Deployment ---
✅ All components verified successfully

========== Deployment Complete ==========
```

### 5. (Optional) Create Bedrock Knowledge Base

For enhanced historical analysis:

1. Go to Bedrock Console > Knowledge Bases
2. Click "Create knowledge base"
3. Name: `resq-disaster-patterns`
4. Configure data source (S3 bucket with historical data)
5. Wait for ingestion to complete
6. Update `.env` with KB ID:
   ```env
   BEDROCK_KB_ID=YOUR_KB_ID_HERE
   ```

### 6. Configure API Keys in Secrets Manager

For production, store API keys in AWS Secrets Manager:

```bash
# Store Twitter token
aws secretsmanager create-secret \
    --name resq/twitter-token \
    --secret-string '{"token":"your_bearer_token_here"}' \
    --region us-east-1

# Store NOAA token
aws secretsmanager create-secret \
    --name resq/noaa-token \
    --secret-string '{"token":"your_noaa_token_here"}' \
    --region us-east-1
```

Update Lambda functions to read from Secrets Manager.

### 7. Test Deployment

```bash
# Run test script
python scripts/test_deployment.py --event-type hurricane --severity 8.0
```

Expected output:
```
Creating test disaster event...
Event ID: test-20241014-123456
Location: {'lat': 29.7604, 'lon': -95.3698}
Type: hurricane

Starting execution of resq-disaster-response-production...
✅ Execution started: arn:aws:states:us-east-1:...
```

### 8. Launch Dashboard

```bash
# Start dashboard
streamlit run dashboard/streamlit_app.py

# Or use installed command
resq-dashboard
```

Dashboard will be available at `http://localhost:8501`

## Verification Steps

### 1. Check CloudFormation Stack

```bash
aws cloudformation describe-stacks \
    --stack-name resq-agent-stack-production \
    --region us-east-1
```

Should show: `"StackStatus": "CREATE_COMPLETE"`

### 2. Verify Lambda Functions

```bash
# List functions
aws lambda list-functions \
    --query 'Functions[?starts_with(FunctionName, `resq-`)].[FunctionName,State]' \
    --output table
```

All should show state: `Active`

### 3. Check DynamoDB Tables

```bash
# List tables
aws dynamodb list-tables --region us-east-1

# Verify disaster-events table
aws dynamodb describe-table \
    --table-name disaster-events \
    --region us-east-1
```

### 4. Test Step Functions

```bash
# List state machines
aws stepfunctions list-state-machines \
    --query 'stateMachines[?contains(name, `resq`)]' \
    --region us-east-1
```

## Troubleshooting

### Issue: CloudFormation Stack Failed

**Solution:**
```bash
# Check stack events
aws cloudformation describe-stack-events \
    --stack-name resq-agent-stack-production \
    --max-items 20

# Delete and retry
aws cloudformation delete-stack \
    --stack-name resq-agent-stack-production

python deploy.py --region us-east-1 --environment production
```

### Issue: Lambda Deployment Failed

**Solution:**
```bash
# Check Lambda logs
aws logs tail /aws/lambda/resq-data-ingestion --follow

# Redeploy specific function
aws lambda update-function-code \
    --function-name resq-data-ingestion \
    --zip-file fileb://build/data_ingestion.zip
```

### Issue: Step Functions Execution Failed

**Solution:**
```bash
# Get execution details
aws stepfunctions describe-execution \
    --execution-arn <your-execution-arn>

# Check specific Lambda logs
aws logs get-log-events \
    --log-group-name /aws/lambda/resq-visual-analysis \
    --log-stream-name <stream-name>
```

### Issue: Bedrock Access Denied

**Solution:**
1. Verify Bedrock is enabled in your region
2. Check IAM role has Bedrock permissions
3. Request model access in Bedrock console

### Issue: Dashboard Won't Load

**Solution:**
```bash
# Check if DynamoDB tables exist
aws dynamodb list-tables

# Verify AWS credentials
aws sts get-caller-identity

# Run dashboard with debug
streamlit run dashboard/streamlit_app.py --logger.level=debug
```

## Cost Estimation

### Monthly Costs (Approximate)

For 100 disaster events/month:

- **Lambda**: ~$50-100
- **DynamoDB**: ~$10-20 (on-demand)
- **S3**: ~$5-15 (with lifecycle policies)
- **Bedrock**: ~$200-500 (varies with token usage)
- **Step Functions**: ~$5
- **Data Transfer**: ~$10-20

**Total: ~$280-660/month**

### Cost Optimization Tips

1. **Use Reserved Capacity** for DynamoDB if usage is predictable
2. **Enable S3 Lifecycle Policies** to archive old imagery
3. **Batch Processing** to reduce Lambda invocations
4. **Optimize Bedrock Prompts** to reduce token usage
5. **Use CloudWatch Logs Insights** instead of exporting all logs

## Production Considerations

### 1. Enable VPC

Edit CloudFormation template:
```yaml
VpcConfig:
  SubnetIds:
    - subnet-xxxxx
    - subnet-yyyyy
  SecurityGroupIds:
    - sg-xxxxx
```

### 2. Set up Monitoring

```bash
# Create CloudWatch dashboard
aws cloudwatch put-dashboard \
    --dashboard-name ResQAgent \
    --dashboard-body file://monitoring/dashboard.json
```

### 3. Configure Backups

```bash
# Enable DynamoDB point-in-time recovery
aws dynamodb update-continuous-backups \
    --table-name disaster-events \
    --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
```

### 4. Set up CI/CD

Configure GitHub Actions or AWS CodePipeline for automated deployments.

### 5. Enable X-Ray Tracing

Already enabled in Lambda functions. View traces in X-Ray console.

## Updating the Deployment

```bash
# Update code only
python deploy.py --skip-build --environment production

# Full update (infrastructure + code)
python deploy.py --environment production
```

## Rollback Procedure

```bash
# Rollback Lambda function
aws lambda update-function-code \
    --function-name resq-orchestrator \
    --s3-bucket deployment-bucket \
    --s3-key previous-version.zip

# Rollback CloudFormation stack
aws cloudformation continue-update-rollback \
    --stack-name resq-agent-stack-production
```

## Next Steps

After successful deployment:

1. ✅ Configure SNS email subscriptions for alerts
2. ✅ Set up CloudWatch alarms
3. ✅ Create Bedrock Knowledge Base (optional)
4. ✅ Run test events
5. ✅ Train your team on the dashboard
6. ✅ Document custom configurations
7. ✅ Set up backup procedures

## Support

For deployment issues:
- Check CloudFormation events
- Review Lambda logs in CloudWatch
- Verify IAM permissions
- Contact: support@resq-agent.com
