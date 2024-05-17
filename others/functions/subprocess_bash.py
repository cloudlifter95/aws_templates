import logging
import os
import json
import datetime

# import cfnresponse
import subprocess

logger = logging.getLogger()
logger.setLevel(logging.INFO)
json.JSONEncoder.default = lambda self,obj: (obj.isoformat() if isinstance(obj,datetime.date) else None)

# import sys
# import shutil

def setup_environment():
    # Define the path to the bash script in the Lambda /tmp directory
    bash_script_path = '/tmp/install_cfnbootstrap.sh'
    
    # Write the bash script content to /tmp directory
    bash_script_content = """#!/bin/bash

# Change to the /tmp directory
cd /tmp

# Update the package list and install pip
yum update -y
yum install -y python3-pip

# Install cfn-bootstrap
pip3 install --target=/tmp https://s3.amazonaws.com/cloudformation-examples/aws-cfn-bootstrap-latest.tar.gz

# Verify the installation
/tmp/bin/cfn-init --version
"""
    
    # Write the content to the bash script file
    with open(bash_script_path, 'w') as file:
        file.write(bash_script_content)
    
    # Make the bash script executable
    os.chmod(bash_script_path, 0o755)
    
    return bash_script_path

def run_bash_script(script_path):
    # Run the bash script
    result = subprocess.run([script_path], capture_output=True, text=True)

    # Print the output and errors, if any
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)

    # Check if the script ran successfully
    if result.returncode == 0:
        print("Script executed successfully.")
    else:
        print(f"Script failed with return code {result.returncode}.")
