import logging
import os
import json
import datetime
import boto3

# import cfnresponse
import subprocess

logger = logging.getLogger()
logger.setLevel(logging.INFO)
json.JSONEncoder.default = lambda self, obj: (
    obj.isoformat() if isinstance(obj, datetime.date) else None)

# import sys
# import shutil


def lambda_handler(event, context):
    logger.info('## EVENT')
    logger.info(json.dumps(event))
    logger.info('## ENVIRONMENT VARIABLES')
    logger.debug('ENV VARS DISPLAY REMOVED')
    logger.info('## CONTEXT VARIABLES')
    logger.info(json.dumps(vars(context)))
    logger.info('## CALLER')
    logger.info(json.dumps(boto3.client('sts').get_caller_identity()))

    CurrentAccountId = context.invoked_function_arn.split(":")[4]

    response = boto3.client('cloudformation').signal_resource(
        StackName=event['StackId'],
        LogicalResourceId=event['LogicalResourceId'],
        UniqueId=event['InstanceId'],  # resource id
        Status=event['Status']
    )

    return {
        'statusCode': 200,
        'body': response
    }
