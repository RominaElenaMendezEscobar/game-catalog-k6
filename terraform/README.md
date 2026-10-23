# 🏗️ Terraform: load testing infrastructure

Creates everything needed to run k6 load tests and generate the PDF report:

| File | Resources |
|---|---|
| `s3.tf` | Bucket `game-catalog-loadtest` (private, encrypted) and the k6 scripts in `scripts/` |
| `ecr.tf` | Repositories `game-catalog-k6` and `game-catalog-report`, with cleanup of old images |
| `network.tf` | Default VPC and subnets, security group with no inbound and HTTPS-only outbound |
| `ecs.tf` | Cluster, log group and task definition of the k6 container |
| `lambda.tf` | Report Lambda (container image, x86_64) and its log group |
| `stepfunction.tf` | State machine `game-catalog-loadtest-pipeline`: RunLoadTest → GenerateReport |
| `iam.tf` | One least-privilege role per component |

The API being tested (API Gateway + search Lambda) belongs to the
[product matching project](https://github.com/RominaElenaMendezEscobar/aws-games-products)
and is not managed here: only its ID is needed.

## Prerequisites

- Terraform >= 1.6, AWS CLI v2 and Docker (AWS CloudShell has the AWS CLI and Docker).
- Amazon Bedrock access to `amazon.nova-pro-v1:0` in `us-east-1`.
- The search API protected with IAM authorization.

To install Terraform in CloudShell:

```bash
curl -sLo /tmp/tf.zip https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip
mkdir -p ~/bin && unzip -o /tmp/tf.zip -d ~/bin && export PATH=$HOME/bin:$PATH
terraform version
```

## First deployment

The Lambda is created from an image, so the image must exist before the Lambda.
That is why the first deployment has three steps:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # set api_id
terraform init

# 1. create only the ECR repositories
terraform apply -target=aws_ecr_repository.k6 -target=aws_ecr_repository.report

# 2. build and push both images
../build-and-push.sh

# 3. create everything else
terraform apply
```

## Run a load test

```bash
aws stepfunctions start-execution \
  --state-machine-arn "$(terraform output -raw state_machine_arn)" \
  --input '{"scenario": "smoke", "label": "baseline"}'
```

Or from the console: Step Functions → `game-catalog-loadtest-pipeline` → Start execution.
The report is saved in `s3://game-catalog-loadtest/runs/<scenario>/<run_id>/report.pdf`.

## Day-to-day changes

| Change | What to run |
|---|---|
| Scenario, queries or `search.js` | `terraform apply` (uploads the scripts again) |
| `entrypoint.sh` or `Dockerfile` of k6 | `./build-and-push.sh k6` |
| Report code or `report/config/*.yaml` | `./build-and-push.sh report` (also updates the Lambda) |
| Any `.tf` file | `terraform apply` |

## Clean up

```bash
terraform destroy
```

The bucket and the ECR repositories are only deleted if they are empty. To delete them
with their content, set `force_destroy = true` in `terraform.tfvars` and run `terraform apply`
before `terraform destroy`.
