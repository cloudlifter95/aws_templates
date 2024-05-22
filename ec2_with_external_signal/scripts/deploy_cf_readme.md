```bash
cd ./ec2_with_external_signal/scripts
bash deploy_cf.sh template_file=../ec2_with_signal.yml stack_name=motest region=eu-central-1 param_file=../ec2_with_signal_params.yml profile=moj9-pg bucket_name=tmpmo-1278213j10q
```
to update a previously provisioned stack, use the uuid parameter to target it:
```bash
cd ./ec2_with_external_signal/scripts
bash deploy_cf.sh template_file=../ec2_with_signal.yml stack_name=motest region=eu-central-1 param_file=../ec2_with_signal_params.yml profile=moj9-pg bucket_name=tmpmo-1278213j10q uuid=46298B91
```