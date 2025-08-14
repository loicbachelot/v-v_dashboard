# v-v_dashboard
Dash app for the Verification and Validation platform for DET’s planned code comparison exercises

# v-v_dashboard (DET Viewer)

Dash app + AWS CDK stack for the DET ``viewer”.  
**What it does:** serves a Dash web app on ECS Fargate behind an ALB, exposes a small API Gateway endpoint for status checks, and invokes a Lambda container during uploads. Data lives in an existing S3 bucket and DynamoDB table.

## Prerequisites

- Docker (with `buildx`)
- AWS CLI v2 (logged in to the target account)
- CDK v2 (`npm i -g aws-cdk` or pip install aws-cdk-lib; CLI is the Node one)
- Permissions to: ECR, ECS, IAM, CloudFormation, EC2, API Gateway, Lambda, DynamoDB
- **Region:** `us-east-2` (Ohio)

> This stack **references** the existing DynamoDB table `DETFileProcessingStatus` and the S3 bucket `benchmark-vv-data`. It does **not** create or delete them.

## One-time (per machine)

```powershell
# Windows PowerShell
$Env:AWS_REGION = "us-east-2"
$Env:AWS_ACCOUNT_ID = (aws sts get-caller-identity --query Account --output text)

# ECR login
aws ecr get-login-password --region $Env:AWS_REGION |
  docker login --username AWS --password-stdin "$Env:AWS_ACCOUNT_ID.dkr.ecr.$Env:AWS_REGION.amazonaws.com"
```

```bash
# macOS/Linux bash
export AWS_REGION=us-east-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws ecr get-login-password --region $AWS_REGION   | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
```

## Build & Push images

> Current tags the CDK stack expects:
> - **Fargate app:** `v-v_dashboard:2.1.14`
> - **Lambda image:** `vv-lambda-upload:2.0.16` (must be built for `linux/amd64`)

```powershell
# Fargate / Dash app
docker build -t v-v_dashboard:2.1.14 .
docker tag  v-v_dashboard:2.1.14 "$Env:AWS_ACCOUNT_ID.dkr.ecr.$Env:AWS_REGION.amazonaws.com/v-v_dashboard:2.1.14"
docker push "$Env:AWS_ACCOUNT_ID.dkr.ecr.$Env:AWS_REGION.amazonaws.com/v-v_dashboard:2.1.14"

# Lambda image
docker buildx build --platform linux/amd64 --provenance=false -t vv-lambda-upload:2.0.16 .
docker tag  vv-lambda-upload:2.0.16 "$Env:AWS_ACCOUNT_ID.dkr.ecr.$Env:AWS_REGION.amazonaws.com/vv-lambda-upload:2.0.16"
docker push "$Env:AWS_ACCOUNT_ID.dkr.ecr.$Env:AWS_REGION.amazonaws.com/vv-lambda-upload:2.0.16"
```

## Deploy

```powershell
cdk deploy
```

At the end you’ll see outputs like:

- `DashboardFargateServiceServiceURL…` → the ALB URL for the Dash UI  
- `StatusAPIEndpoint` → API Gateway base URL (ends with `/prod/`)

You can re-print them any time:

```powershell
aws cloudformation describe-stacks --stack-name DashboardStack --region us-east-2 `
  --query "Stacks[0].Outputs[].{K:OutputKey,V:OutputValue}" --output table
```

## Smoke tests

**1) Dash UI loads**

Open the ALB URL from the outputs in a browser. Initial load may take ~30–90s right after deploy as the task warms up.

**2) Status API works**

Install once: `pip install awscurl`

```powershell
# Missing params → error (expected)
awscurl --service execute-api --region us-east-2 "<API_BASE>/status"

# With params (table empty returns {} which is OK)
awscurl --service execute-api --region us-east-2 "<API_BASE>/status?userId=test-user&fileId=example.csv"
```

**3) End-to-end trigger (optional sandbox test)**

Upload a dummy file to the existing bucket with user metadata:

```powershell
Set-Content -Path dummy.csv -Value "test"
aws s3 cp dummy.csv s3://benchmark-vv-data/upload/dummy.csv --metadata userid=test-user --region us-east-2
```

Then query:

```powershell
awscurl --service execute-api --region us-east-2 "<API_BASE>/status?userId=test-user&fileId=dummy.csv"
```

> Note: This is a **non-destructive** test and should not spam anyone. The failure-path Lambda writes a status row; if nothing writes, you’ll get `{}` which just means no row yet.

## Changing image versions later

- Fargate app tag is set in `cdk/cdk_stack.py`:
  ```py
  image=ecs.ContainerImage.from_ecr_repository(repository, "2.1.14")
  ```
- Lambda image tag is set here:
  ```py
  _lambda.DockerImageCode.from_ecr(repository=repo, tag="2.0.16")
  ```

To use different tags, update those strings, push new images with matching tags, then `cdk deploy`.

## Troubleshooting

- **Region or repo mismatch** → Ensure you are in `us-east-2` and both repos (`v-v_dashboard`, `vv-lambda-upload`) exist and contain the tags you reference.

You can check your current AWS CLI region with:
```bash
aws configure get region
```
If it’s not us-east-2, set it temporarily for your session:
```bash
export AWS_REGION=us-east-2   # macOS/Linux
setx AWS_REGION us-east-2     # Windows PowerShell

```
Also confirm that both required ECR repositories exist in this region and contain the image tags you reference:
```bash
aws ecr describe-repositories --region us-east-2 --repository-names v-v_dashboard vv-lambda-upload

```
If they don’t exist, you’ll need to create them or update the CDK/commands to point to the correct repositories.

## Cleanup

If you’re done with a test environment:

```powershell
cdk destroy
```

This tears down the **stack resources** (VPC, endpoints, ALB, ECS service/task, API Gateway, Lambda functions, IAM roles/policies, etc.).  
It **does not** delete:
- The existing **DynamoDB table** `DETFileProcessingStatus`
- The existing **S3 bucket** `benchmark-vv-data`
- Your **ECR repositories/images`


## Acknowledgments
