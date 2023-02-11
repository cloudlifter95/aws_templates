import json
from base64 import b64decode, b64encode
import datetime

json.JSONEncoder.default = lambda self,obj: (obj.isoformat() if (isinstance(obj, datetime.datetime) or isinstance(obj,datetime.date)) else None)
# some useful constants
STATUS_OK = 'Ok'
STATUS_DROPPED = 'Dropped'
STATUS_FAIL = 'ProcessingFailed'

class DroppedRecordException(Exception):
    """ This exception can be raised if a record needs to be skipped/dropped """
    pass
    
def lambda_handler(event, context):
    """ This is the main Lambda entry point """
    print('event:', event)
    return {
        'records': list(map(process_record, event['records'])),
    }

def process_record(record):
    """ Invoked once for each record (raw base64-encoded data) """
    data = json.loads(b64decode(record['data']))
    try:
        new_data = transform_data(data)  # manipulate/validate record
        record['data'] = b64encode((json.dumps(new_data) + "\n").encode("utf-8"))  # encode as bytes then b64 re-encode and add newline (for Athena)
    except DroppedRecordException:
        record['result'] = STATUS_DROPPED  # skip
    except Exception as e:
        print(e)
        record['result'] = STATUS_FAIL  # generic error
    else:
        record['result'] = STATUS_OK  # all good
    return record

  
def transform_data(data):
    """ Invoked once for each record """
    print("Processing data: %s" % data)

    # example: you can skip records
    # if 'invalid stuff' in data:
    #     raise DroppedRecordException()

    # example: you can add new fields
    # data['new_value'] = True

    data['stackname'] = data['detail']['stack-id'].split(':')[-1].split('/')[1]
    data['stackstatus'] = data['detail']['status-details']['status']

    return data
  