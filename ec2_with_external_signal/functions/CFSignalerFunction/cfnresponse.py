import json
import logging
from urllib.request import HTTPError, build_opener, HTTPHandler, Request

SUCCESS = "SUCCESS"
FAILED = "FAILED"

# Configure logging
logging.basicConfig(format='%(levelname)s:%(module)s:%(message)s', level=logging.INFO)


def send(event, context, response_status, response_data=None, reason=None, physical_resource_id=None):
    response_data = response_data or {}
    response_body = json.dumps(
        {
            'Status': response_status,
            'Reason': reason or f"See the details in CloudWatch Log Stream: {context.log_stream_name}",
            'PhysicalResourceId': physical_resource_id or context.log_stream_name,
            'StackId': event['StackId'],
            'RequestId': event['RequestId'],
            'LogicalResourceId': event['LogicalResourceId'],
            'Data': response_data
        }
    )

    opener = build_opener(HTTPHandler)
    request = Request(event['ResponseURL'], data=response_body.encode('utf-8'))
    request.add_header('Content-Type', 'application/json')
    request.add_header('Content-Length', len(response_body.encode('utf-8')))
    request.get_method = lambda: 'PUT'
    
    try:
        response = opener.open(request)
        logging.info("Request status code: %s", response.getcode())
        logging.info("Request status message: %s", response.msg)
        return True
    except HTTPError as exc:
        logging.error("Failed executing HTTP request: %s", exc.code)
        return False
