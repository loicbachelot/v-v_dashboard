# v-v\_dashboard (DET Viewer)

Dash app + AWS CDK stack for the DET \`\`viewer”.  
**What it does:** serves a Dash web app on ECS Fargate behind an ALB, exposes a small API Gateway endpoint for status checks, and invokes a Lambda container during uploads. Data lives in an existing S3 bucket and DynamoDB table.

-----

## CI/CD Pipeline (Recommended)

This project is configured with an automated CI/CD pipeline using GitHub Actions. To deploy changes, you simply need to push your code to the `ci/test` branch.

### CI (Continuous Integration)

  * **Trigger:** Runs automatically on pushes to `ci/test` and on pull requests to `main`.
  * **Actions:** Runs fast Python checks using Ruff, a linter that acts like a spell and grammar checker for code to ensure style consistency. It also runs tests with Pytest and performs sanity builds for the Dockerfiles to ensure they are valid.

### CD (Continuous Delivery)

  * **Trigger:** Runs automatically on pushes to `ci/test`. Can also be triggered manually.
  * **Actions:** Securely authenticates to AWS using OpenID Connect (OIDC), this allows GitHub Actions to access AWS withoutt needing to store long-lived secret keys. The workflow then builds and pushes the application and Lambda images to ECR, deploys the full infrastructure stack using the AWS CDK, and runs a smoke test to verify the live endpoints.

-----

## How to Deploy

The recommended method is to use the automated pipeline.

### Step 1: Push Your Code

Commit your code changes and push them to the `ci/test` branch.

```bash
git push origin ci/test
```

This will automatically trigger both the `ci` and `deploy-dev` workflows. You can monitor their progress in the "Actions" tab of the GitHub repository.

### Step 2: Verify the Deployment (Smoke Test)

After the `deploy-dev` workflow succeeds, you can manually verify the live endpoints by fetching their URLs from the deployed CloudFormation stack.

**Bash:**

```bash
STACK="DashboardStack"
REGION="us-east-2"

# Get the Application Load Balancer URL
ALB_URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceURL'].OutputValue" --output text)

# Get the API Health Check URL
API_URL=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='StatusAPIHealthURL'].OutputValue" --output text)

echo "--- Checking ALB URL: $ALB_URL ---"
curl -fsS "$ALB_URL" | head -n 10

echo ""
echo "--- Checking API Health URL: $API_URL ---"
curl -fsS "$API_URL"
```

### Step 3: Destroy the Environment (When Finished)

To save costs, destroy the development stack when you are done. The preferred method is to trigger the destroy workflow.

```bash
gh workflow run destroy-dev.yml --ref ci/test
```

-----

## Local Development Setup

These steps are for developers who need to run and test the application on their local machine.

### Prerequisites
* Docker (with `buildx`)
* AWS CLI v2
* Python 3.9+
* Node.js 20+ and CDK v2 (`npm i -g aws-cdk`)

### 1. Environment and Dependencies
First, create an isolated Python virtual environment and install the required packages.

```bash
# Create the virtual environment
python -m venv .venv

# Activate the environment (macOS/Linux)
source .venv/bin/activate

# Or activate on Windows PowerShell
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r cdk/requirements.txt
````

### 2\. AWS Account Login (One-Time)

Log your local machine and Docker client into the target AWS account.

```bash
# Login to AWS (e.g., with SSO)
# aws sso login --profile your-profile-name

# Login Docker to the ECR registry
export AWS_REGION=us-east-2
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
```

After completing these steps, your local environment is ready for running manual builds or deployments with the `cdk` command.



## Acknowledgments

<table>
  <tr>
    <td align="center" valign="middle">
      <img src="assets/favicon.ico" alt="CRESCENT Logo" width="150" />
    </td>
    <td align="center" valign="middle">
      <img src="assets/USNSF_Logo.png" alt="NSF Logo" width="450" />
    </td>
  </tr>
</table>

CRESCENT is funded by NSF cooperative agreement #2225286 and is also supported by the Pacific Gas and Electric Company (PG&E).