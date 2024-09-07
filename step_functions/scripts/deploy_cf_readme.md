Create stack:
```bash
cd ./step_functions
bash deploy_cf.sh template_file=../stack.yml stack_name=mjteststep region=eu-central-1 param_file=../stack_params.yml profile=moj9-pg bucket_name=tmpmo-1278213j10q
```
==> capture STACK UUID <UUID>

Update stack:
```bash
bash deploy_cf.sh template_file=../stack.yml stack_name=mjteststep region=eu-central-1 param_file=../stack_params.yml profile=moj9-pg bucket_name=tmpmo-1278213j10q uuid=<UUID>
```