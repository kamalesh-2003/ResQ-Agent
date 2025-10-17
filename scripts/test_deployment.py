"""
Test script for ResQ-Agent deployment
Sends a test disaster event through the system
"""

import boto3
import json
from datetime import datetime
import argparse


def create_test_event(event_type='hurricane', severity=7.5):
    """Create a test disaster event"""
    return {
        'event_id': f'test-{datetime.now().strftime("%Y%m%d-%H%M%S")}',
        'location': {
            'lat': 29.7604,  # Houston, TX
            'lon': -95.3698
        },
        'event_type': event_type,
        'timestamp': datetime.now().isoformat(),
        'state': 'TX',
        'radius_km': 50,
        'severity_estimate': severity
    }


def trigger_workflow(region='us-east-1', environment='production'):
    """Trigger the disaster response workflow"""
    print("Creating test disaster event...")

    event = create_test_event()
    print(f"Event ID: {event['event_id']}")
    print(f"Location: {event['location']}")
    print(f"Type: {event['event_type']}")

    # Trigger Step Functions
    sfn_client = boto3.client('stepfunctions', region_name=region)
    state_machine_name = f'resq-disaster-response-{environment}'

    # Get state machine ARN
    response = sfn_client.list_state_machines()
    state_machine = next((sm for sm in response['stateMachines']
                         if sm['name'] == state_machine_name), None)

    if not state_machine:
        print(f"❌ State machine {state_machine_name} not found")
        return

    print(f"\nStarting execution of {state_machine_name}...")

    response = sfn_client.start_execution(
        stateMachineArn=state_machine['stateMachineArn'],
        name=f"test-execution-{event['event_id']}",
        input=json.dumps(event)
    )

    execution_arn = response['executionArn']
    print(f"✅ Execution started: {execution_arn}")
    print(f"\nMonitor execution in AWS Console:")
    print(f"https://{region}.console.aws.amazon.com/states/home?region={region}#/executions/details/{execution_arn}")

    return execution_arn


def check_execution_status(execution_arn, region='us-east-1'):
    """Check status of execution"""
    sfn_client = boto3.client('stepfunctions', region_name=region)

    response = sfn_client.describe_execution(executionArn=execution_arn)

    print(f"\nExecution Status: {response['status']}")
    print(f"Start Date: {response['startDate']}")

    if response['status'] in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
        print(f"End Date: {response.get('stopDate', 'N/A')}")

        if response['status'] == 'SUCCEEDED':
            print("✅ Execution completed successfully!")
            output = json.loads(response.get('output', '{}'))
            print(f"\nFinal Confidence Score: {output.get('verification', {}).get('Payload', {}).get('overall_confidence', 'N/A')}")
        else:
            print(f"❌ Execution {response['status']}")
            if 'error' in response:
                print(f"Error: {response['error']}")
                print(f"Cause: {response.get('cause', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(description='Test ResQ-Agent deployment')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--environment', default='production', help='Environment')
    parser.add_argument('--event-type', default='hurricane',
                       choices=['hurricane', 'earthquake', 'flood', 'fire', 'tornado'],
                       help='Type of disaster event')
    parser.add_argument('--severity', type=float, default=7.5,
                       help='Severity estimate (0-10)')
    parser.add_argument('--check-execution', help='Check status of existing execution')

    args = parser.parse_args()

    if args.check_execution:
        check_execution_status(args.check_execution, args.region)
    else:
        trigger_workflow(args.region, args.environment)


if __name__ == '__main__':
    main()
