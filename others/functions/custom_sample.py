import logging
import os
import json
import datetime
import boto3

import cfnresponse


logger = logging.getLogger()
logger.setLevel(logging.INFO)
json.JSONEncoder.default = lambda self,obj: (obj.isoformat() if isinstance(obj,datetime.date) else None)


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

    try:
        if event['RequestType'] == 'Delete':
            logger.info('Incoming RequestType: Delete operation // nothing to do') 
            responseData = {"Message": "Incoming RequestType: Delete operation // nothing to do" }
            logger.info("responseData:") 
            logger.info(json.dumps(responseData)) 
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
            return

        elif event['RequestType'] == 'Update':
            logger.info('Incoming RequestType: Update operation // nothing to do') 
            responseData = {"Message": "Incoming RequestType: Update operation // nothing to do" }
            logger.info("responseData:") 
            logger.info(json.dumps(responseData)) 
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
            return
        
        elif event['RequestType'] == 'Create':
            logger.info('Incoming RequestType: Create operation // nothing to do') 
            responseData = {"Message": "Incoming RequestType: Create operation // nothing to do" }
            logger.info("responseData:") 
            logger.info(json.dumps(responseData)) 
            cfnresponse.send(event, context, cfnresponse.SUCCESS, responseData)
            return

        else:
            raise Exception("Incoming RequestType unknown. throw exception.")
    
    except Exception as err:
        logger.error(err)
        reasonData = {"Exception": str(err)}
        cfnresponse.send(event, context, cfnresponse.FAILED, {}, reason=str(reasonData))
    
