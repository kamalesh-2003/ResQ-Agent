"""
ResQ-Agent Deployment Script
Automates deployment of infrastructure and Lambda functions to AWS
"""

import boto3
import zipfile
import os
import json
import time
import yaml
import argparse
from pathlib import Path
import subprocess

class ResQDeployer:
    """Handles deployment of ResQ-Agent to AWS"""

    def __init__(self, region='us-east-1', environment='production'):
        self.region = region
        self.environment = environment

        # AWS clients
        self.cf_client = boto3.client('cloudformation', region_name=region)
        self.lambda_client = boto3.client('lambda', region_name=region)
        self.s3_client = boto3.client('s3', region_name=region)
        self.sfn_client = boto3.client('stepfunctions', region_name=region)
        self.iam_client = boto3.client('iam', region_name=region)

        # Paths
        self.root_dir = Path(__file__).parent
        self.infra_dir = self.root_dir / 'infrastructure'
        self.lambda_dir = self.infra_dir / 'lambda_functions'

        print(f"Initialized deployer for region: {region}, environment: {environment}")

    def deploy_all(self):
        """Deploy all components"""
        print("\n========== ResQ-Agent Deployment ==========\n")

        steps = [
            ("Deploying CloudFormation Stack", self.deploy_cloudformation),
            ("Building Lambda Packages", self.build_lambda_packages),
            ("Deploying Lambda Functions", self.deploy_lambda_functions),
            ("Deploying Step Functions", self.deploy_step_functions),
            ("Verifying Deployment", self.verify_deployment),
        ]

        for step_name, step_func in steps:
            print(f"\n--- {step_name} ---")
            try:
                step_func()
                print(f"✅ {step_name} completed successfully")
            except Exception as e:
                print(f"❌ {step_name} failed: {str(e)}")
                raise

        print("\n========== Deployment Complete ==========\n")
        self.print_deployment_info()

    def deploy_cloudformation(self):
        """Deploy CloudFormation stack"""
        stack_name = f'resq-agent-stack-{self.environment}'
        template_path = self.infra_dir / 'cloudformation' / 'core-stack.yaml'

        print(f"Deploying stack: {stack_name}")

        with open(template_path, 'r') as f:
            template_body = f.read()

        try:
            # Check if stack exists
            self.cf_client.describe_stacks(StackName=stack_name)
            print(f"Stack {stack_name} exists, updating...")

            self.cf_client.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=[
                    {'ParameterKey': 'EnvironmentName', 'ParameterValue': self.environment}
                ],
                Capabilities=['CAPABILITY_NAMED_IAM']
            )

            print("Waiting for stack update to complete...")
            waiter = self.cf_client.get_waiter('stack_update_complete')
            waiter.wait(StackName=stack_name)

        except self.cf_client.exceptions.ClientError as e:
            if 'does not exist' in str(e):
                print(f"Creating new stack: {stack_name}")

                self.cf_client.create_stack(
                    StackName=stack_name,
                    TemplateBody=template_body,
                    Parameters=[
                        {'ParameterKey': 'EnvironmentName', 'ParameterValue': self.environment}
                    ],
                    Capabilities=['CAPABILITY_NAMED_IAM'],
                    Tags=[
                        {'Key': 'Project', 'Value': 'ResQ-Agent'},
                        {'Key': 'Environment', 'Value': self.environment}
                    ]
                )

                print("Waiting for stack creation to complete...")
                waiter = self.cf_client.get_waiter('stack_create_complete')
                waiter.wait(StackName=stack_name)
            else:
                raise

        print(f"Stack {stack_name} deployed successfully")

    def build_lambda_packages(self):
        """Build Lambda deployment packages"""
        print("Building Lambda packages...")

        # Create build directory
        build_dir = self.root_dir / 'build'
        build_dir.mkdir(exist_ok=True)

        # Install minimal Lambda dependencies
        print("Installing minimal Lambda dependencies...")
        lambda_requirements = self.root_dir / 'requirements-lambda.txt'
        if not lambda_requirements.exists():
            print("Warning: requirements-lambda.txt not found, using requirements.txt")
            lambda_requirements = self.root_dir / 'requirements.txt'

        subprocess.run([
            'pip', 'install', '-r', str(lambda_requirements),
            '-t', str(build_dir / 'python')
        ], check=True)

        # Copy source code
        print("Copying source code...")
        for module in ['agents', 'data_ingestion']:
            src_dir = self.root_dir / module
            dst_dir = build_dir / 'python' / module
            if src_dir.exists():
                subprocess.run(['xcopy', str(src_dir), str(dst_dir), '/E', '/I', '/Y'],
                             shell=True, check=True)

        # Create Lambda packages
        lambda_functions = [
            'data_ingestion',
            'visual_analysis',
            'orchestrator',
            'resource_optimizer',
            'verification'
        ]

        for func_name in lambda_functions:
            print(f"Packaging {func_name}...")
            zip_path = build_dir / f'{func_name}.zip'

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add dependencies
                python_dir = build_dir / 'python'
                for root, dirs, files in os.walk(python_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(build_dir / 'python')
                        zipf.write(file_path, arcname)

                # Add Lambda function
                func_file = self.lambda_dir / f'{func_name}.py'
                if func_file.exists():
                    zipf.write(func_file, f'{func_name}.py')

            print(f"Created {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.2f} MB)")

    def deploy_lambda_functions(self):
        """Deploy Lambda functions"""
        print("Deploying Lambda functions...")

        # Get Lambda role ARN and S3 bucket from CloudFormation
        stack_name = f'resq-agent-stack-{self.environment}'
        response = self.cf_client.describe_stacks(StackName=stack_name)
        outputs = response['Stacks'][0].get('Outputs', [])
        role_arn = next((o['OutputValue'] for o in outputs if o['OutputKey'] == 'LambdaExecutionRoleArn'), None)
        s3_bucket = next((o['OutputValue'] for o in outputs if o['OutputKey'] == 'DataLakeBucketName'), None)

        if not role_arn:
            raise Exception("Lambda execution role not found in stack outputs")
        if not s3_bucket:
            raise Exception("S3 bucket not found in stack outputs")

        lambda_functions = {
            'resq-data-ingestion': 'data_ingestion',
            'resq-visual-analysis': 'visual_analysis',
            'resq-orchestrator': 'orchestrator',
            'resq-resource-optimizer': 'resource_optimizer',
            'resq-verification': 'verification'
        }

        build_dir = self.root_dir / 'build'

        for func_name, zip_name in lambda_functions.items():
            print(f"Deploying {func_name}...")

            zip_path = build_dir / f'{zip_name}.zip'
            s3_key = f'lambda/{zip_name}.zip'

            # Upload to S3 first
            print(f"  Uploading {zip_name}.zip to S3...")
            self.s3_client.upload_file(str(zip_path), s3_bucket, s3_key)

            try:
                # Try to update existing function
                self.lambda_client.update_function_code(
                    FunctionName=func_name,
                    S3Bucket=s3_bucket,
                    S3Key=s3_key
                )
                print(f"  Updated {func_name}")

            except self.lambda_client.exceptions.ResourceNotFoundException:
                # Create new function
                print(f"  Creating new function: {func_name}")

                self.lambda_client.create_function(
                    FunctionName=func_name,
                    Runtime='python3.11',
                    Role=role_arn,
                    Handler=f'{zip_name}.lambda_handler',
                    Code={'S3Bucket': s3_bucket, 'S3Key': s3_key},
                    Timeout=900 if 'visual' in func_name else 300,
                    MemorySize=10240 if 'visual' in func_name else 3008,
                    Environment={
                        'Variables': {
                            'RESQ_ENVIRONMENT': self.environment
                        }
                    },
                    Tags={
                        'Project': 'ResQ-Agent',
                        'Environment': self.environment
                    }
                )

            # Wait for function to be active
            time.sleep(2)

        print("All Lambda functions deployed")

    def deploy_step_functions(self):
        """Deploy Step Functions state machine"""
        print("Deploying Step Functions...")

        # Get role ARN
        stack_name = f'resq-agent-stack-{self.environment}'
        response = self.cf_client.describe_stacks(StackName=stack_name)
        outputs = response['Stacks'][0].get('Outputs', [])
        role_arn = next((o['OutputValue'] for o in outputs if o['OutputKey'] == 'StepFunctionsRoleArn'), None)

        if not role_arn:
            raise Exception("Step Functions role not found in stack outputs")

        # Load workflow definition
        workflow_path = self.infra_dir / 'step_functions' / 'disaster_response_workflow.json'
        with open(workflow_path, 'r') as f:
            definition = f.read()

        # Replace account ID and region placeholders
        account_id = boto3.client('sts').get_caller_identity()['Account']
        definition = definition.replace('ACCOUNT_ID', account_id)
        definition = definition.replace('us-east-1', self.region)  # Fix hardcoded region

        state_machine_name = f'resq-disaster-response-{self.environment}'

        try:
            # Get existing state machine
            response = self.sfn_client.list_state_machines()
            existing = next((sm for sm in response['stateMachines']
                           if sm['name'] == state_machine_name), None)

            if existing:
                print(f"Updating state machine: {state_machine_name}")
                self.sfn_client.update_state_machine(
                    stateMachineArn=existing['stateMachineArn'],
                    definition=definition,
                    roleArn=role_arn
                )
            else:
                print(f"Creating state machine: {state_machine_name}")
                self.sfn_client.create_state_machine(
                    name=state_machine_name,
                    definition=definition,
                    roleArn=role_arn,
                    type='STANDARD',
                    tags=[
                        {'key': 'Project', 'value': 'ResQ-Agent'},
                        {'key': 'Environment', 'value': self.environment}
                    ]
                )

            print("Step Functions deployed successfully")

        except Exception as e:
            print(f"Error deploying Step Functions: {str(e)}")
            raise

    def verify_deployment(self):
        """Verify deployment is successful"""
        print("Verifying deployment...")

        # Check CloudFormation stack
        stack_name = f'resq-agent-stack-{self.environment}'
        response = self.cf_client.describe_stacks(StackName=stack_name)
        stack_status = response['Stacks'][0]['StackStatus']

        if 'COMPLETE' not in stack_status:
            raise Exception(f"Stack is in unexpected state: {stack_status}")

        # Check Lambda functions
        lambda_functions = [
            'resq-data-ingestion',
            'resq-visual-analysis',
            'resq-orchestrator',
            'resq-resource-optimizer',
            'resq-verification'
        ]

        for func_name in lambda_functions:
            try:
                response = self.lambda_client.get_function(FunctionName=func_name)
                if response['Configuration']['State'] != 'Active':
                    raise Exception(f"Lambda {func_name} is not active")
            except self.lambda_client.exceptions.ResourceNotFoundException:
                raise Exception(f"Lambda {func_name} not found")

        print("✅ All components verified successfully")

    def print_deployment_info(self):
        """Print deployment information"""
        print("\n========== Deployment Information ==========")
        print(f"Region: {self.region}")
        print(f"Environment: {self.environment}")
        print(f"Stack Name: resq-agent-stack-{self.environment}")
        print("\nNext Steps:")
        print("1. Configure API keys in AWS Secrets Manager")
        print("2. Set up Bedrock Knowledge Base and update config")
        print("3. Run the dashboard: streamlit run dashboard/streamlit_app.py")
        print("4. Test with a sample disaster event")
        print("\nDashboard will be available at: http://localhost:8501")
        print("==========================================\n")


def main():
    parser = argparse.ArgumentParser(description='Deploy ResQ-Agent to AWS')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--environment', default='production',
                       choices=['development', 'staging', 'production'],
                       help='Deployment environment')
    parser.add_argument('--skip-build', action='store_true',
                       help='Skip building Lambda packages')

    args = parser.parse_args()

    deployer = ResQDeployer(region=args.region, environment=args.environment)

    try:
        if args.skip_build:
            print("Skipping Lambda package build...")
            deployer.deploy_cloudformation()
            deployer.deploy_lambda_functions()
            deployer.deploy_step_functions()
            deployer.verify_deployment()
        else:
            deployer.deploy_all()

    except KeyboardInterrupt:
        print("\n\nDeployment cancelled by user")
    except Exception as e:
        print(f"\n\n❌ Deployment failed: {str(e)}")
        raise


if __name__ == '__main__':
    main()
