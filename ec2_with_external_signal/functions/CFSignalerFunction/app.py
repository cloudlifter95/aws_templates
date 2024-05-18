import logging
import os
import json
import datetime
import boto3
from botocore.config import Config
import re

import cfnresponse
import subprocess

logger = logging.getLogger()
logger.setLevel(logging.INFO)
json.JSONEncoder.default = lambda self, obj: (
    obj.isoformat() if isinstance(obj, datetime.date) else None)

# import sys
# import shutil

config = Config(
    retries={
        'max_attempts': 10,
        'mode': 'standard'
    }
)

CFN_CLIENT = boto3.client('cloudformation', config=config)
SSM_CLIENT = boto3.client('ssm', config=config)
EC2_CLIENT = boto3.client('ec2', config=config)
EVENT_CLIENT = boto3.client('events', config=config)

COUNTER_PARAMETER_INIT_VALUE = "enabled_increment_0"


def cfn_signal_resource(event, status="SUCCESS"):
    response = CFN_CLIENT.signal_resource(
        StackName=event['StackId'],
        LogicalResourceId=event['LogicalResourceId'],
        UniqueId=event['InstanceId'],  # resource id
        Status="SUCCESS"  # | "FAILURE"
    )
    return response


def describe_cf_ec2_instance(cfn_client, event, logical_resource_id, context):
    # Get the stack resource status
    response = CFN_CLIENT.describe_stack_resource(
        stack_name=event['ResourceProperties']['StackName']
        StackName=stack_name,
        LogicalResourceId=logical_resource_id
    )
    return response


def check_resource_status(cfn_client, event, logical_resource_id, cf_ec2_dict context):
    stack_name = event['ResourceProperties']['StackName']
    logical_resource_id = logical_resource_id
    resource_status = None  # todo if stays none, should be handled with incident

    try:
        response = describe_cf_ec2_instance(cf_ec2_dict)

        resource_status = response['StackResourceDetail']['ResourceStatus']
        print(f"Resource status for {logical_resource_id} in stack {
              stack_name}: {resource_status}")

        # responseData = {'ResourceStatus': resource_status}
        # cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
    except Exception as e:
        print(f"Failed to get resource status: {e}")
        raise Exception('EC2InstanceResourceNotFound')
        # responseData = {'Error': str(e)}
        # cfnresponse.send(event, context, cfnresponse.FAILED, responseData)

    return resource_status


def initialize_counter(event):
    counter_parameter_name = event['ResourceProperties'].get(
        'SchedulerSSMParameter', None)
    if counter_parameter_name is None:
        raise Exception('NoCounter')

    try:
        # Set the parameter value
        response = SSM_CLIENT.put_parameter(
            Name=counter_parameter_name,
            Value=COUNTER_PARAMETER_INIT_VALUE,
            Type='String',
            Overwrite=True
        )

        print(f"Parameter {counter_parameter_name} set to {
              COUNTER_PARAMETER_INIT_VALUE}")
    except Exception as e:
        print(f"Failed to set parameter value: {e}")
        raise Exception('ParamInitFailed')


def load_counter_value(event):
    counter_parameter_name = event['ResourceProperties'].get(
        'SchedulerSSMParameter', None)
    if counter_parameter_name is None:
        raise Exception('NoCounter')
    response = SSM_CLIENT.get_parameter(
        Name=counter_parameter_name,
        # WithDecryption=True  # Use WithDecryption=True if the parameter is encrypted
    )

    return response['Parameter']['Value']


def is_success(value):
    if 'success' in value:
        return True
    else:
        return False


def is_increment_below_threshold(value="enabled_increment_0", threshold):
    if value.split('_')[2] < threshold:
        return True
    else:
        return False

# change check or add additional checks here


def run_checks(event, cf_ec2_dict):
    success = False
    instance_id = cf_ec2_dict['StackResourceDetail']['StackResourceDetail']
    success = check_ec2_instance(instance_id)

    return success


def add_success_suffix(event, previous_value):
    counter_parameter_name = event['ResourceProperties'].get(
        'SchedulerSSMParameter', None)
    if counter_parameter_name is None:
        raise Exception('NoCounter')

    try:
        # Set the parameter value
        response = SSM_CLIENT.put_parameter(
            Name=counter_parameter_name,
            Value=f"{previous_value}_success",
            Type='String',
            Overwrite=True
        )

        print(f"Parameter {counter_parameter_name} set to {
              previous_value}_success")
    except Exception as e:
        print(f"Failed to set parameter value: {e}")
        raise Exception('ParamSuccessSetFailed')

def increment_counter(event, value):
    numbers = re.findall(r'\d+', value)
    if not numbers:
        raise ValueError("No number found in the string")

    last_number = numbers[-1]
    new_number = str(int(last_number) + 1)
    incremented_value = re.sub(r'\d+$', new_number, value)

    counter_parameter_name = event['ResourceProperties'].get(
        'SchedulerSSMParameter', None)
    if counter_parameter_name is None:
        raise Exception('NoCounter')

    try:
        # Set the parameter value
        response = SSM_CLIENT.put_parameter(
            Name=counter_parameter_name,
            Value=incremented_value,
            Type='String',
            Overwrite=True
        )

        print(f"Parameter {counter_parameter_name} set to {
              incremented_value}")
    except Exception as e:
        print(f"Failed to set parameter value: {e}")
        raise Exception('ParamIncrementFailed')


def check_ec2_instance(instance_id):
    try:
        # Describe the instance to get its status
        response = EC2_CLIENT.describe_instance_status(
            InstanceIds=[instance_id],
            IncludeAllInstances=True
        )

        if len(response['InstanceStatuses']) == 0:
            status = "Instance not found"
            initialized = False
        else:
            instance_status = response['InstanceStatuses'][0]['InstanceState']['Name']
            system_status = response['InstanceStatuses'][0]['SystemStatus']['Status']
            instance_status_ok = response['InstanceStatuses'][0]['InstanceStatus']['Status']

            is_running = instance_status == 'running'
            is_initialized = system_status == 'ok' and instance_status_ok == 'ok'

            if is_running and is_initialized:
                status = "Running and Initialized"
                initialized = True
            else:
                status = "Not fully initialized"
                initialized = False

        print(f"EC2 instance {instance_id} status: {status}")

        responseData = {
            'InstanceId': instance_id,
            'Status': status,
            'Initialized': initialized
        }
        return responseData
    except Exception as e:
        print(f"Failed to describe instance status: {e}")
        responseData = {'Error': str(e)}
        raise Exception('EC2StatusCheckFailed')

def disable_aws_scheduler(event):
    rule_name = event['ResourceProperties'].get('Event', None)
    if rule_name is None:
        raise Exception('NoRuleNameInEvent')
    try:
        EVENT_CLIENT.disable_rule(Name=rule_name)
        print(f"Scheduler '{rule_name}' disabled successfully.")
    except EVENT_CLIENT.exceptions.ResourceNotFoundException:
        print(f"Scheduler '{rule_name}' not found.")
        raise Exception('NoEventRuleFound')
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise Exception('EventRuleError')

def generate_incident():
    return handle_incident({"incident": "title", "message": "message"})


def handle_incident(incident_dict):
    print(incident_dict)
    # replace with handler code. or leave like this for demo


def lambda_handler(event, context):
    status = [200, 'SUCCEEDED']
    logger.info('## EVENT')
    logger.info(json.dumps(event))
    logger.info('## ENVIRONMENT VARIABLES')
    logger.debug('ENV VARS DISPLAY REMOVED')
    logger.info('## CONTEXT VARIABLES')
    logger.info(json.dumps(vars(context)))
    logger.info('## CALLER')
    logger.info(json.dumps(boto3.client('sts').get_caller_identity()))

    CurrentAccountId = context.invoked_function_arn.split(":")[4]

    # from custom
    if 'RequestType' in event and 'StackId' in event and 'RequestId' in event and event['RequestId'] != '__Event__':
        print("Lambda is being invoked from a CloudFormation custom resource.")
        # Perform custom resource logic here
        try:
            pass
        except:
            status = [400, 'FAILED']
            responseData = {"status": ', '.join(status)}
        cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
    else:
        print("Lambda is not being invoked from a CloudFormation custom resource. ")
        # from scheduler
        if event['RequestId'] == '__Event__':
            print("Lambda called from event")
        # from else
        else:
            print("Lambda called manually. Pass")
            status[1] = 'PASSED'

    return {
        'statusCode': status[0],
        'body': status[1]
    }
