import sys
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock
from io import StringIO
from datetime import datetime, timezone
import os
import logging
logging.debug(f"syspath: {sys.path}")
logging.debug(os.environ)


#### ENV VAR INIT SETUP for successful import ####
os.environ['LogicalResourceId'] = 'mock_logical_resource_id'
os.environ['SchedulerName'] = 'mock_scheduler_name'
os.environ['Threshold'] = '-1'
os.environ['SchedulerSSMParameter'] = 'mock_scheduler_ssm_parameter'
os.environ['StackName'] = 'mock_stack_name'

# import CFSignalerFunction.app as svc
import CFSignalerFunction.app as svc
#######################

# apply marker
pytestmark = pytest.mark.use_setup_cfnsignaler_module

# tests


@patch('CFSignalerFunction.app.EC2_CLIENT.describe_instances')
@patch('sys.stdout', new_callable=StringIO)
def test_enrich_event_with_ec2_resource_id(mock_stdout, mock_describe_instances, event_from_scheduler):
    # First subtest
    mock_response = {
        'Reservations': [
            {
                'Instances': [
                    {'InstanceId': 'instance_id1', 'LaunchTime': '2024-05-28T12:00:00Z'},
                    {'InstanceId': 'instance_id2', 'LaunchTime': '2024-05-29T12:00:00Z'}
                ]
            }
        ]
    }
    mock_describe_instances.return_value = mock_response

    result_event = svc.enrich_event_with_ec2_resource_id(event_from_scheduler)
    assert result_event['ResourceProperties']['ec2_resource_id'] == 'instance_id2'

    # Second subtest
    mock_response = {
        'Reservations': []
    }
    mock_describe_instances.return_value = mock_response
    result_event = svc.enrich_event_with_ec2_resource_id(event_from_scheduler)
    # Capture the printed output
    printed_output = mock_stdout.getvalue().strip()
    logging.info(f"printed_output:{printed_output}")

    assert printed_output == "No instances found with the specified tag."
    assert 'ec2_resource_id' not in result_event

# @mock_aws # not needed as session fixture now takes care of that


def test_of_setup():
    logging.debug(boto3.client('ec2').describe_instances())
    logging.debug(os.environ)

@patch('sys.stdout', new_callable=StringIO)
def test_of_get_stack_status(mock_stdout):
    cf_client = boto3.client('cloudformation')
    stack_name = 'MyTestStack'
    template_body = '''
    {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Resources": {
        "MyEC2Instance": {
        "Type": "AWS::EC2::Instance",
        "Properties": {
            "InstanceType": "t2.micro",
            "ImageId": "ami-12345678",
            "KeyName": "my-key-pair"
        }
        }
    }
    }
    '''

    # Create the CloudFormation stack
    response = cf_client.create_stack(
        StackName=stack_name,
        TemplateBody=template_body,
        TimeoutInMinutes=5,
        OnFailure='ROLLBACK'
    )
    logging.debug(response)

    tested_function_response = svc.get_stack_status(stack_name)
    assert tested_function_response == 'CREATE_COMPLETE'


    ### Second subtest

