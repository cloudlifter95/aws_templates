# Update below parameters
# export profile if necessary

# Parameters
Region=eu-central-1
StackName=ingestion
StackFile=./ingestion-pipeline.yml
BucketName=mybuckfortest78129
#############


echo "Creating packaging bucket ${BucketName} if not exists ..."
if aws s3 ls "s3://$BucketName" 2>&1 | grep -q 'NoSuchBucket'; then
    aws s3api create-bucket --bucket ${BucketName} --region ${Region} --create-bucket-configuration LocationConstraint=${Region}
    echo "Bucket created."
else
    echo "Bucket already exists."
fi


echo "Packaging stack template $StackFile ..."
aws cloudformation package \
    --template-file $StackFile \
    --output-template-file ${StackFile}_packaged \
    --s3-bucket ${BucketName} \
    --s3-prefix ${StackName} \

echo "Deploying ${StackName} in ${Region}..." ;

aws cloudformation deploy \
    --region ${Region} \
    --no-fail-on-empty-changeset \
    --template-file ${StackFile}_packaged \
    --stack-name $StackName \
    --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND CAPABILITY_NAMED_IAM \
    --tags stage=dev \
