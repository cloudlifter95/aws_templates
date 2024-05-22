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
LOGICAL_RESOURCE_ID = os.environ['LogicalResourceId']
SCHEDULER_NAME = os.environ['SchedulerName']
THRESHOLD = int(os.environ['Threshold'])


def cfn_signal_resource(event, status="SUCCESS"):
    response = CFN_CLIENT.signal_resource(
        StackName=event['ResourceProperties']['StackName'],
        LogicalResourceId=LOGICAL_RESOURCE_ID,
        UniqueId=event['ResourceProperties']['InstanceId'],  # resource physical id
        Status=status  # "SUCCESS" | "FAILURE"
    )
    return response



def describe_cf_ec2_instance(event, logical_resource_id, context=None):
    # Get the stack resource status
    response = CFN_CLIENT.describe_stack_resource(
        StackName=event['ResourceProperties']['StackName'],
        LogicalResourceId=logical_resource_id
    )
    return response


def check_resource_status(event, cf_ec2_dict, context=None):
    stack_name = event['ResourceProperties']['StackName']
    resource_status = None  # todo if stays none, should be handled with incident

    try:
        # response = describe_cf_ec2_instance(cf_ec2_dict)

        resource_status = cf_ec2_dict['StackResourceDetail']['ResourceStatus']
        print(f"Resource status in stack {stack_name}: {resource_status}")

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

        print(f"Parameter {counter_parameter_name} set to {COUNTER_PARAMETER_INIT_VALUE}")
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


def is_increment_below_threshold(value, threshold):
    if value.split('_')[2] < threshold:
        return True
    else:
        return False

# change check or add additional checks here


def run_checks(event, cf_ec2_dict):
    success = False
    instance_id = cf_ec2_dict['StackResourceDetail']['PhysicalResourceId']
    if (check_ec2_instance(instance_id) == 'Running and Initialized'):
        success = True

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

        print(f"Parameter {counter_parameter_name} set to {previous_value}_success")
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

        print(f"Parameter {counter_parameter_name} set to {incremented_value}")
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


def enable_aws_scheduler(scheduler_name):
    rule_name = scheduler_name
    try:
        EVENT_CLIENT.enable_rule(Name=rule_name)
        print(f"Scheduler '{rule_name}' enabled successfully.")
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
    logger.info('## EVENT')
    logger.info(json.dumps(event))
    logger.info('## ENVIRONMENT VARIABLES')
    logger.debug('ENV VARS DISPLAY REMOVED')
    logger.info('## CONTEXT VARIABLES')
    logger.info(json.dumps(vars(context)))
    logger.info('## CALLER')
    logger.info(json.dumps(boto3.client('sts').get_caller_identity()))

    try:
        current_account_id = context.invoked_function_arn.split(":")[4]
        status = ["200", 'SUCCEEDED']
        responseData = {"status": ', '.join(status)}
        # check_resource_status(event=event, cf_ec2_dict=cf_ec2_dict)
        cf_ec2_dict = describe_cf_ec2_instance(
            event=event, logical_resource_id=LOGICAL_RESOURCE_ID, context=context)

        # from custom
        if 'RequestType' in event and 'StackId' in event and 'RequestId' in event and event['RequestId'] != '__Event__':
            print("Lambda is being invoked from a CloudFormation custom resource.")
            if event['RequestType'] == 'Delete' or event['RequestType'] == 'Create':  # nothing to perform
                print(f"Signal is {event['RequestType']}. Pass")
            else:
                # Perform custom resource logic here
                try:
                    initialize_counter(event)
                    enable_aws_scheduler(SCHEDULER_NAME)
                except:
                    status = ["400", 'FAILED']
                    responseData = {"status": ', '.join(status)}
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
        else:
            print("Lambda is not being invoked from a CloudFormation custom resource. ")
            # from scheduler
            if event['RequestId'] == '__Event__':
                print("Lambda called from event")
                counter_value = load_counter_value(event)
                if 'disabled' in counter_value:
                    raise Exception('RuleDisabled')
                if (is_success(counter_value)):
                    initialize_counter(event)  # reset
                    disable_aws_scheduler(event)
                    cfn_signal_resource(event, "SUCCESS")
                    status = ["200", 'SUCCEEDED']
                else:
                    if (not is_increment_below_threshold(counter_value, THRESHOLD)):
                        generate_incident()
                        initialize_counter(event)  # reset
                        disable_aws_scheduler(event)
                        status = ["200", 'INCIDENT_RAISED']
                    else:
                        if (run_checks(event, cf_ec2_dict)):
                            add_success_suffix(event, counter_value)
                            status = ["200", f"Success_suffix_appended_{counter_value}"]
                        increment_counter(event, counter_value)
                        status = ["200", f"Counter_incrementer_{counter_value}"]
            # from else
            else:
                print("Lambda called manually. Pass")
                status = ["200", 'PASSED']
    except Exception as e:
        logger.error(e)
        status = ["400", 'FAILED']
        if 'RequestType' in event and 'StackId' in event and 'RequestId' in event and event['RequestId'] != '__Event__':
            responseData = {"status": ', '.join(status)}
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
        else:
            pass
    return {
        'statusCode': status[0],
        'body': status[1]
    }
