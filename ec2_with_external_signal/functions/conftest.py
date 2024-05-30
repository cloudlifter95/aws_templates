# conftest.py
import pytest
import boto3
import os
from moto import mock_aws
import logging

# @pytest.fixture(autouse=True)
# def mock_aws_credentials(monkeypatch):
#     # Set fake credentials
#     monkeypatch.setenv("AWS_ACCESS_KEY_ID", "fake_access_key")
#     monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake_secret_key")
#     monkeypatch.setenv("AWS_SESSION_TOKEN", "fake_session_token")

# @pytest.fixture(autouse=True)
# def mock_aws_credentials():
#     # Set fake credentials
#     os.environ['AWS_ACCESS_KEY_ID'] = 'AK_from_fixture'
#     os.environ['AWS_SECRET_ACCESS_KEY'] = 'SK_from_fixture'
#     os.environ['AWS_SESSION_TOKEN'] = 'ST_from_fixture'

@pytest.fixture(scope='module')
def create_ssm_parameter():
    with mock_aws():
        ssm_client = boto3.client('ssm')

        def _create_ssm_parameter(name, value):
            ssm_client.put_parameter(
                Name=name,
                Value=value,
                Type='String'
            )

        yield _create_ssm_parameter


@pytest.fixture(scope='module')
def create_eventbridge_rule():
    with mock_aws():
        eventbridge_client = boto3.client('events')

        def _create_eventbridge_rule(name, schedule_expression):
            response = eventbridge_client.put_rule(
                Name=name,
                ScheduleExpression=schedule_expression,
                State='ENABLED'
            )
            return response['RuleArn']

        yield _create_eventbridge_rule


@pytest.fixture(scope='module')
def setup_environment_and_env_vars(create_ssm_parameter, create_eventbridge_rule):
    
    os.environ['StackName'] = 'MyStack'

    param_name = f"{os.environ['StackName']}/CFSignalerFunction/SchedulerFlag"
    create_ssm_parameter(name=param_name, value="enabled_increment_0")

    rule_arn = create_eventbridge_rule(name='test-rule', schedule_expression='cron(0 12 * * ? *)')
    eventbridge_client = boto3.client('events')
    response = eventbridge_client.describe_rule(Name='test-rule')

    os.environ['LogicalResourceId'] = 'EC2Instance'
    os.environ['SchedulerName'] = f"CFSignalerRule-{os.environ['StackName']}"
    os.environ['Threshold'] = '2'
    os.environ['SchedulerSSMParameter'] = param_name


@pytest.fixture(scope='function')
def create_two_instances_sequentially():
    with mock_aws():
        ec2 = boto3.resource('ec2')

        instance1 = ec2.create_instances(
            ImageId='ami-12345678',
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [{'Key': 'tag:aws:cloudformation:stack-name', 'Value': f"{os.environ['StackName']}"}]
                }
            ]
        )[0]

        instance2 = ec2.create_instances(
            ImageId='ami-12345678',
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [{'Key': 'tag:aws:cloudformation:stack-name', 'Value': f"{os.environ['StackName']}"}]
                }
            ]
        )[0]

        yield {'ec2': ec2, 'instance1': instance1, 'instance2': instance2}

@pytest.fixture(scope='function')
def event_from_scheduler():
    yield {
    "RequestId": "__Event__",
    "ResourceProperties": {
        "StackName": os.environ['StackName'],
        "Event": f"CFSignalerRule-{os.environ['StackName']}"
    }
}
