UUID=$(od -x /dev/urandom | head -1 | awk '{OFS="-"; print $2$3$4$5$6$7$8$9}')
StackName=""    # ToChange
StackTemplate="../lambda_url.yml"  # ToChange
ArtifactsS3Bucket=""   # ToChange
BuildNumber=$UUID
region="eu-central-1" #ToChange
TrustedOrg="" # ToChange

echo "aws cloudformation package $StackTemplate"
aws cloudformation package \
    --template-file $StackTemplate \
    --output-template-file $StackTemplate.packaged \
    --s3-bucket $ArtifactsS3Bucket \
    --s3-prefix ${BuildNumber} \
    --region ${region}

echo "Deploy $StackName ($StackTemplate)"
aws cloudformation deploy \
    --region $region \
    --no-fail-on-empty-changeset \
    --template-file $StackTemplate.packaged \
    --stack-name $StackName-$UUID \
    --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND CAPABILITY_NAMED_IAM \
    --parameter-overrides \
    TrustedOrg=$TrustedOrg \
    # --tags $Tags
