############ IMPORTS AND SETTINGS ##############

from hmac import new
import logging
import os
import json
import datetime
import boto3
import uuid
from operator import attrgetter
# import cfnresponse
from botocore.exceptions import ClientError
# from time import sleep
from pprint import pprint as pp
import sys; sys.path.insert(0, './lib'); # sys.path.append('./lib') #; print(sys.path)
import get_accounts_recursive
# from .lib import get_accounts_recursive # import for package mode


OS_MAX_DEPTH = os.environ["MAX_DEPTH"]
logger = logging.getLogger()
logger.setLevel(logging.INFO)
json.JSONEncoder.default = lambda self, obj: (obj.isoformat() if (
    isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date)) else None)

########## IMPORTS AND SETTINGS END HERE ############

def lambda_handler(event, context):
    logger.info('## EVENT')
    logger.info(json.dumps(event))
    logger.info('## ENVIRONMENT VARIABLES')
    logger.info(json.dumps(dict(os.environ)))
    logger.info('## CONTEXT VARIABLES')
    logger.info(json.dumps(vars(context)))
    logger.info('## CALLER')
    logger.info(json.dumps(boto3.client('sts').get_caller_identity()))

    reponse = []

    try:
        response = get_accounts_recursive.get_accounts_recursive(boto3.client('organizations').list_roots()['Roots'][0]['Id'], MAX_DEPTH=int(OS_MAX_DEPTH))
        # print(len(response))
        # pp(response)

    except Exception as err:
        logger.error(err, exc_info=True)

    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }
