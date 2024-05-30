import logging
import os
import json
import datetime
import boto3
from botocore.config import Config
import re
import sys
import types
import time
from botocore.exceptions import ClientError

from . import cfnresponse
from functools import wraps

###################### LOGGING 1/2 #####################
logger = logging.getLogger()
logger.setLevel(logging.INFO)
json.JSONEncoder.default = lambda self, obj: (
    obj.isoformat() if isinstance(obj, datetime.date) else None)


def log_function_call(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Calling function: {func.__name__} with args: {args} and kwargs: {kwargs}")
        result = func(*args, **kwargs)
        logger.info(f"{func.__name__} returned {result}")
        return result
    return wrapper


def decorate_all_functions(module):
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if isinstance(attr, types.FunctionType):
            setattr(module, attr_name, log_function_call(attr))

# decorate functions unitarily with wrapper: @log_function_call
# decorate all module functions with wrapper:
"""
# must be at the end of the file
current_module = sys.modules[__name__]
decorate_all_functions(current_module)
"""
#####################################################
config = Config(
    retries={
        'max_attempts': 10,
        'mode': 'standard'
    }
)

EC2_INIT_WAIT = 300

CFN_CLIENT = boto3.client('cloudformation', config=config)
SSM_CLIENT = boto3.client('ssm', config=config)
EC2_CLIENT = boto3.client('ec2', config=config)
EVENT_CLIENT = boto3.client('events', config=config)

COUNTER_PARAMETER_INIT_VALUE = "enabled_increment_0"
LOGICAL_RESOURCE_ID = os.environ['LogicalResourceId']
SCHEDULER_NAME = os.environ['SchedulerName']
THRESHOLD = int(os.environ['Threshold'])
SCHEDULER_SSM_PARAMETER = os.environ['SchedulerSSMParameter']
STACKNAME = os.environ['StackName']

def event_from_monitored_ec2_instance(event):
    expected_tags = {
        "aws:cloudformation:stack-name": STACKNAME,
        "aws:cloudformation:logical-id": LOGICAL_RESOURCE_ID
    }
    try:
        tag_specification_set = event["detail"]["requestParameters"]["tagSpecificationSet"]["items"]
    except KeyError:
        # If the structure is not as expected, return False
        return False
    
    # Check if any of the tag specifications match the expected tags
    for tag_spec in tag_specification_set:
        if tag_spec.get("resourceType") == "instance":
            tags = {tag["key"]: tag["value"] for tag in tag_spec.get("tags", [])}
            print("Found tags:", tags)
            print("Expected tags:", expected_tags)
            if all(tags.get(key) == value for key, value in expected_tags.items()):
                return True
    
    return False

def get_stack_status(stack_name):
    try:
        response = CFN_CLIENT.describe_stacks(StackName=stack_name)
        stack_status = response['Stacks'][0]['StackStatus']
        return stack_status
    except CFN_CLIENT.exceptions.ClientError as e:
        print(f"Error fetching stack status: {e}")
        return None

def enrich_event_with_ec2_resource_id(event, cf_tag_key='tag:aws:cloudformation:stack-name'):
    response = EC2_CLIENT.describe_instances(
        Filters=[
            {
                'Name': cf_tag_key,
                'Values': [event['ResourceProperties']['StackName']]
            }
        ]
    )
    # logging.info(response)
    instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instances.append(instance)
    if not instances:
        print("No instances found with the specified tag.")
        return event

    newest_instance = max(instances, key=lambda x: x['LaunchTime'])

    event['ResourceProperties']['ec2_resource_id'] = newest_instance['InstanceId']

    return event


def cfn_signal_resource(event, status="SUCCESS"):
    response = CFN_CLIENT.signal_resource(
        StackName=event['ResourceProperties']['StackName'],
        LogicalResourceId=LOGICAL_RESOURCE_ID,
        UniqueId=event['ResourceProperties']['ec2_resource_id'],  # resource physical id
        Status=status  # "SUCCESS" | "FAILURE"
    )
    return response


# def describe_cf_ec2_instance(event, logical_resource_id, context=None):
#     # Get the stack resource status
#     response = CFN_CLIENT.describe_stack_resource(
#         StackName=event['ResourceProperties']['StackName'],
#         LogicalResourceId=logical_resource_id
#     )
#     return response


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
    counter_parameter_name = SCHEDULER_SSM_PARAMETER
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
    return load_counter_value(event)


# @log_function_call
def load_counter_value(event):
    counter_parameter_name = SCHEDULER_SSM_PARAMETER
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
    if int(value.split('_')[2]) < threshold:
        return True
    else:
        return False

# change check or add additional checks here


def run_checks(event):
    success = False
    instance_id = event['ResourceProperties']['ec2_resource_id']
    instance_init=check_ec2_instance(instance_id)
    if (instance_init.get('Initialized', None)):
        ###* Checks and actions go here. @Dev
        #*  
        if 1==1: # example test
            success = True
        #*
        ###*

    # Teardown
    print('Checks done! Tearing down..')
    if instance_init.get('StopInstanceFlag', None):
        try:
            print("Shutting down vm which was initially stopped")
            EC2_CLIENT.stop_instances(InstanceIds=[instance_id])
        except Exception as e:
            print('Error shutting down VM. Passing', e)

    return success


def add_success_suffix(event, previous_value):
    counter_parameter_name = SCHEDULER_SSM_PARAMETER
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

    return load_counter_value(event)


def increment_counter(event, value):
    numbers = re.findall(r'\d+', value)
    if not numbers:
        raise ValueError("No number found in the string")

    last_number = numbers[-1]
    new_number = str(int(last_number) + 1)
    incremented_value = re.sub(r'\d+$', new_number, value)

    counter_parameter_name = SCHEDULER_SSM_PARAMETER
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
    return load_counter_value(event)


def start_instance(instance_id, max_wait=EC2_INIT_WAIT):
    """
    Start a stopped EC2 instance and wait until it's running, up to a maximum wait time.

    :return: Boolean, True if the instance was started and is running and is initialized within the wait time, else False.
    """

    try:
        # Start the instance
        EC2_CLIENT.start_instances(InstanceIds=[instance_id])
        print(f"Starting instance {instance_id}. Waiting for it to be 'running' and initialized...")

        start_time = time.time()
        while True:
            response = EC2_CLIENT.describe_instance_status(InstanceIds=[instance_id])
            instance_status = response['InstanceStatuses']

            if not instance_status:
                # Instance status is not available yet
                print(f"Instance {instance_id} status is not available yet. Waiting...")
            else:
                state = instance_status[0]['InstanceState']['Name']
                system_status = instance_status[0]['SystemStatus']['Status']
                instance_status_check = instance_status[0]['InstanceStatus']['Status']

                print(f"Current state: {state}, System status: {system_status}, Instance status: {instance_status_check}")

                if state == 'running' and system_status == 'ok' and instance_status_check == 'ok':
                    print(f"Instance {instance_id} is now running and initialized.")
                    return True

            # Check elapsed time
            elapsed_time = time.time() - start_time
            if elapsed_time >= max_wait:
                print(f"Instance {instance_id} did not reach 'running' state within {max_wait / 60} minutes.")
                return False

            print(f"Waiting for instance {instance_id} to be 'running' and 'initialized'...")
            time.sleep(10)
                
    except ClientError as e:
        print(f"Could not start instance {instance_id}. Error: {e}")
        return False

def check_ec2_instance(instance_id):
    stop_instance_flag = False
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
            is_stopped = instance_status == 'stopped'
            is_initialized = system_status == 'ok' and instance_status_ok == 'ok'

            if is_running and is_initialized:
                status = "Running and Initialized"
                initialized = True
            else:
                if is_stopped:
                    cmd_state = start_instance(instance_id) # start and wait
                    if cmd_state:
                        stop_instance_flag = True
                        status = "Running and Initialized"
                        initialized = True
                    else:
                        status = "Not fully initialized"
                        initialized = False
                        print('waiting for next iteration')
                else:
                    status = "Not fully initialized"
                    initialized = False
                    print('waiting for next iteration')

        print(f"EC2 instance {instance_id} status: {status}")

        responseData = {
            'InstanceId': instance_id,
            'Status': status,
            'Initialized': initialized,
            'StopInstanceFlag': stop_instance_flag
        }
        return responseData
    except Exception as e:
        print(f"Failed to describe instance status: {e}")
        responseData = {'Error': str(e)}
        raise Exception('EC2StatusCheckFailed')


def get_aws_scheduler_state(rule_name):
    try:
        response = EVENT_CLIENT.describe_rule(Name=rule_name)
        state = response['State']
        print(f"State of rule '{rule_name}': {state}")
        return state
    except EVENT_CLIENT.exceptions.ResourceNotFoundException:
        print(f"Rule '{rule_name}' not found.")
        raise Exception('NoEventRuleFound')
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise Exception('EventRuleError')

def disable_aws_scheduler(event):
    rule_name = event['ResourceProperties'].get('Event', None)
    get_aws_scheduler_state(rule_name)
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

    return get_aws_scheduler_state(rule_name)

def get_instance_tag_value(instance_id, tag_key):
    try:
        tag_value = next((tag['Value'] for tag in EC2_CLIENT.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0].get('Tags', []) if tag['Key'] == tag_key), "TAG_NOT_SET")
        return tag_value
    except Exception as e:
        print(f"Error fetching tag value: {e}")
        return None

def tag_ec2_instance(instance_id, tag_value=""):
    tag_key = 'transaction.health'
    valid_values = ["complete", "compromised", "no_data"]

    if tag_value not in valid_values:
        raise ValueError(f"Invalid tag value: {tag_value}. Must be one of {valid_values}")

    EC2_CLIENT.create_tags(
        Resources=[instance_id],
        Tags=[{'Key': tag_key, 'Value': tag_value}]
    )
    print(f"EC2 Tag {tag_key} set to {tag_value}")

    return get_instance_tag_value(instance_id, tag_key)


def enable_aws_scheduler(scheduler_name):
    rule_name = scheduler_name
    get_aws_scheduler_state(rule_name)
    try:
        EVENT_CLIENT.enable_rule(Name=rule_name)
        print(f"Scheduler '{rule_name}' enabled successfully.")
    except EVENT_CLIENT.exceptions.ResourceNotFoundException:
        print(f"Scheduler '{rule_name}' not found.")
        raise Exception('NoEventRuleFound')
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        raise Exception('EventRuleError')
    return get_aws_scheduler_state(rule_name)


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
        print(event)
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
            # from master scheduler - initializor
            if 'detail' in event and "managementEvent" in event['detail']:
                # temporal loop initialization
                print("Lambda is being invoked from master event bridge rule. Verifying if event is coming from monitored ec2 instance.")
                if event_from_monitored_ec2_instance(event):
                    if get_stack_status(STACKNAME) == "UPDATE_IN_PROGRESS":
                        print('Stack in update in progress')
                        print("Init steps starting ... ")
                        try:
                            initialize_counter(event)
                            enable_aws_scheduler(SCHEDULER_NAME)
                        except:
                            status = ["400", 'FAILED']
                            responseData = {"status": ', '.join(status)}
                    else:
                        print('Stack creation. Pass')
                        status = ["200", 'PASSED']
                else:
                    print('RunInstances event not from monitored ec2 instance. Pass')
                    status = ["200", 'PASSED']
            else:
                # from scheduler
                event = enrich_event_with_ec2_resource_id(event)
                if event['RequestId'] == '__Event__':
                    print("Lambda called from scheduler event bridge rule. temporal loop engaged ...")
                    counter_value = load_counter_value(event)
                    if 'disabled' in counter_value:
                        raise Exception('RuleDisabled')
                    if (is_success(counter_value)):
                        initialize_counter(event)  # reset
                        disable_aws_scheduler(event)
                        tag_ec2_instance(instance_id=event['ResourceProperties']['ec2_resource_id'], tag_value="complete")
                        cfn_signal_resource(event, "SUCCESS")
                        status = ["200", 'SUCCEEDED']
                    else:
                        if (not is_increment_below_threshold(counter_value, THRESHOLD)): # failure to converge
                            tag_ec2_instance(instance_id=event['ResourceProperties']['ec2_resource_id'], tag_value="compromised")
                            generate_incident()
                            initialize_counter(event)  # reset
                            disable_aws_scheduler(event)
                            status = ["200", 'INCIDENT_RAISED']
                        else:
                            if (run_checks(event)):
                                add_success_suffix(event, counter_value)
                                status = ["200", f"Success_suffix_appended_{counter_value}"]
                            else:
                                increment_counter(event, counter_value)
                            counter_value = load_counter_value(event)
                            status = ["200", f"Counter_incrementer:{counter_value}"]
                # from else
                else:
                    print("Lambda called manually or unhandled signal. Pass")
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

########################## LOGGING 2/2 ############################
# Apply the decorator to all functions in the current module
current_module = sys.modules[__name__]
decorate_all_functions(current_module)
###############################################################