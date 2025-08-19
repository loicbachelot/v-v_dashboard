# CI/CD quickstart

### CI (continuous integration) — what runs on PRs

- Fast Python checks: Ruff lint + pytest (if tests/ exists).

- Sanity builds for both Dockerfiles (no push; just make sure they still build).

- Runs automatically on pull_request and on pushes to main and ci/test.

### CD (continuous delivery) — what runs on demand ( Deploy uses AWS OIDC so no repository AWS keyss required and runs only from the ci/test branch for now.)

- Builds app & lambda images → pushes to ECR → CDK deploys infra → smoke test (ALB + /status).

- Separate destroy workflow to tear down the stack.

# Run CI locally (same checks as the PR workflow)

```bash
# in repo root
python -m pip install --upgrade pip
pip install -r requirements.txt || true
pip install ruff pytest

# lint
ruff check .

# unit tests (if you have them)
pytest -q

# make sure Dockerfiles still build
docker build -t v-v_dashboard:ci .
DOCKER_BUILDKIT=0 docker build -t vv-lambda-upload:ci -f lambda_process_uploads/Dockerfile lambda_process_uploads
```

# Trigger CD

```bash
# Uses default image tag = commit SHA
gh workflow run deploy-dev.yml --ref ci/test

# (optional) override the tag
gh workflow run deploy-dev.yml --ref ci/test --field tag=2.0.17
```


# Smoke test (verify URLs)
```bash
STACK=DashboardStack REGION=us-east-2

ALB=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?contains(OutputKey, 'ServiceURL')].OutputValue" --output text)

APIS=$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
  --query "Stacks[0].Outputs[?contains(OutputKey, 'APIEndpoint')].OutputValue" --output text)

echo "ALB: $ALB"; curl -fsS "$ALB" | head -n 5
for b in $APIS; do curl -fsS "${b%/}/status"; echo; done

```

# PowerShell
```bash
$STACK="DashboardStack"; $REGION="us-east-2"

$ALB  = aws cloudformation describe-stacks --stack-name $STACK --region $REGION `
  --query "Stacks[0].Outputs[?contains(OutputKey, 'ServiceURL')].OutputValue" --output text
$APIs = aws cloudformation describe-stacks --stack-name $STACK --region $REGION `
  --query "Stacks[0].Outputs[?contains(OutputKey, 'APIEndpoint')].OutputValue" --output text

Write-Host "ALB: $ALB"
curl.exe --max-time 15 -fsS $ALB | more

$APIs.Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object {
  $u = ($_).TrimEnd('/') + "/status"
  Write-Host "Checking $u"
  curl.exe --max-time 15 -fsS $u | more
}

```

# Destroy dev stack
``` bash
# Preferred
gh workflow run destroy-dev.yml --ref ci/test

# Fallback (CLI)
aws cloudformation delete-stack --stack-name DashboardStack --region us-east-2
aws cloudformation wait stack-delete-complete --stack-name DashboardStack --region us-east-2

```

#### next things to do 

CI/CD polish checklist
- [ ] Switch GitHub Actions to AWS OIDC (remove access keys)
- [ ] Add Ruff + Pytest steps to ci.yml
- [ ] Enable pip caching
- [ ] Enable CodeQL (Python)
- [ ] Add branch protections (require CI)
