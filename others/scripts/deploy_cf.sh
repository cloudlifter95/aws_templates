#!/usr/bin/env bash

set -e
# set -o errexit
set -o pipefail
# set -o nounset

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if AWS credentials are configured
if [ -z "$(aws configure get aws_access_key_id)" ] || [ -z "$(aws configure get aws_secret_access_key)" ]; then
    echo "AWS credentials are not configured. Please run 'aws configure' to set them up."
    exit 1
fi

# Parse named arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        template_file=*)
            template_file="${1#*=}"
            ;;
        stack_name=*)
            stack_name="${1#*=}"
            ;;
        uuid=*)
            uuid="${1#*=}"
            ;;
        region=*)
            region="${1#*=}"
            ;;
        profile=*)
            profile="${1#*=}"
            ;;
        param_file=*)
            param_file="${1#*=}"
            ;;
        bucket_name=*)
            bucket_name="${1#*=}"
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo "Options:"
            echo "  template_file=<template_file_path>  Path to CloudFormation template file"
            echo "  stack_name=<stack-name>             Name for the CloudFormation stack"
            echo "  region=<region>                     AWS region to deploy the stack"
            echo "  uuid=<uuid>                         (Optional) UUID to append to stack name"
            echo "  profile=<profile>                   (Optional) AWS CLI profile to use"
            echo "  param_file=<param_file>             (Optional) Path to parameter file in YAML format"
            echo "  bucket_name=<bucket_name>           (Optional) Bucket to use for packaging if referenced"
            exit 0
            ;;
        *)
            echo "Invalid argument: $1"
            exit 1
            ;;
    esac
    shift
done

# Check if required arguments are provided
if [ -z "$template_file" ] || [ -z "$stack_name" ]; then
    echo "Usage: $0 template_file=<template_file_path> stack_name=<stack-name> region=<region> [uuid=<uuid>] [profile=<profile>] [param_files=<param_files>]"
    exit 1
fi

# Generate UUID if not provided
if [ -z "$uuid" ]; then
    uuid=$(uuidgen | awk -F '-' '{print $3$4}')
fi

####### Functions #######
parse_yaml () {
    local YAML_FILE=${1}
    local PARAM_TO_SET=${2}
    
    if [[ ! -f ${YAML_FILE} ]]
    then 
        echo "ERROR: Unable to find file '${YAML_FILE}' for parsing!"
        exit 1
    fi

    # ok, this'll need a bit of explaining :) 
    # cat ${YAML_FILE} - read the file
    # grep -v -e '---'  - ignore any lines with '---' (well formed yaml)'
    # grep -v '#' - ignore any comments
    # sed -e "s/:[^:\/\/]/='/g;s/$/'/g;s/ *=/=/g" - sed magic to replace ': ' with '=' and enclose the value in single quotes
    # tr '\n' ' ' - replace newlines with spaces cos we want everything on one line
    local output=$(cat ${YAML_FILE}|grep -v -e '---'|grep -v '#'|sed -e "s/:[^:\/\/]/='/g;s/$/'/g;s/ *=/=/g"|tr '\n' ' ')
    # echo "OUTPUT: ${output}"
    eval "${PARAM_TO_SET}=\"${output}\""
}
###########################

####### Start #######

# UUID=$(uuidgen | awk -F '-' '{print $3$4}')

get_aws_account_id() {
    local caller_identity
    caller_identity="aws sts get-caller-identity"
    if [ -n "$profile" ]; then
        caller_identity+=" --profile $profile"
    fi
    local account_id
    account_id=$($caller_identity | jq -r .Account)
    echo "$account_id"
}


# template_file="$1"
# stack_name="$2"

# If a UUID is provided as the third argument, update the stack name
if [ $# -eq 3 ]; then
    stack_name="$stack_name-$uuid"
else
    stack_name="$stack_name-$uuid"
fi

echo "Deploying ..."
deploy_command="aws cloudformation deploy \
    --no-fail-on-empty-changeset \
    --template-file \"$template_file\" \
    --stack-name \"$stack_name\" \
    --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND CAPABILITY_NAMED_IAM \
    --region \"$region\""

# Add profile option if specified
if [ -n "$profile" ]; then
    deploy_command+=" --profile $profile"
fi

# Add parameter file if specified
if [ -n "$param_file" ]; then
    echo "Parsing parameters file"
    parse_yaml ${param_file} stack_params
    echo $stack_params
    deploy_command+=" --parameter-overrides ${stack_params%% }"
fi

echo "Summary:"
echo "  Template File: $template_file"
echo "  Stack Name: $stack_name"
echo "  UUID: $uuid"
echo "  Region: $region"
echo "  Account: $(get_aws_account_id)"
echo "  Profile: $profile"
echo "  Parameter file: $param_file"
echo "  Extracted Parameters: $stack_params"
echo "  Bucket name: $bucket_name"
echo ""

if [ -n "$bucket_name" ]; then
    echo "Bucket referenced. Template will be packaged"
    echo "Packaging $template_file"
    aws cloudformation package \
        --template-file $template_file \
        --output-template-file "$template_file.packaged" \
        --s3-bucket ${bucket_name} \
        --s3-prefix ${stack_name} \
        --profile $profile \

    echo "Rewriting deploy command"
    # Perform find and replace within deploy_command
    deploy_command="${deploy_command//\"$template_file\"/\"$template_file.packaged\"}"

fi

echo $deploy_command
eval "$deploy_command"

# Check the deployment status
if [ $? -eq 0 ]; then
    echo "CloudFormation stack '$stack_name' deployed successfully."
    echo "Append uuid=$uuid to this command to update"
else
    echo "Failed to deploy CloudFormation stack '$stack_name'."
fi