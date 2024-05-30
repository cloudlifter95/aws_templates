import sys
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import os
import logging
logging.info(f"syspath: {sys.path}")
logging.info(os.environ)


#### ENV VAR INIT SETUP for successful import ####
os.environ['LogicalResourceId'] = 'mock_logical_resource_id'
os.environ['SchedulerName'] = 'mock_scheduler_name'
os.environ['Threshold'] = '-1'
os.environ['SchedulerSSMParameter'] = 'mock_scheduler_ssm_parameter'
os.environ['StackName'] = 'mock_stack_name'

# import CFSignalerFunction.app as svc
from CFSignalerFunction.app import enrich_event_with_ec2_resource_id
#######################


@patch('CFSignalerFunction.app.EC2_CLIENT.describe_instances')
def test_enrich_event_with_ec2_resource_id(mock_describe_instances, setup_environment_and_env_vars, event_from_scheduler):
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

    result_event = enrich_event_with_ec2_resource_id(event_from_scheduler)
    assert result_event['ResourceProperties']['ec2_resource_id'] == 'instance_id2'