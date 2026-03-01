#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# deploy.sh — Build, push, migrate, and deploy the Workflow Orchestrator.
#
# Usage:
#   STAGE=dev  ./scripts/deploy.sh
#   STAGE=prod ./scripts/deploy.sh
#   STAGE=dev  ./scripts/deploy.sh --skip-migrate
#
# Prefix resolution:
#   main / master                 → wo        (stack: wo-dev)
#   feature/wo-42-some-feature    → wo-42     (stack: wo-42-dev)
#   bug/wo-7-fix-retries          → wo-7      (stack: wo-7-dev)
#   hotfix/wo-99-critical         → wo-99     (stack: wo-99-dev)
#   Override:  PREFIX=wo-99 ./scripts/deploy.sh
#
# Prerequisites:
#   - AWS CLI v2 configured (aws sts get-caller-identity works)
#   - Docker running
#   - CDK bootstrapped (npx cdk bootstrap)
# ──────────────────────────────────────────────────────────────
set -euo pipefail

STAGE="${STAGE:-dev}"
SKIP_MIGRATE=false
AWS_REGION="${AWS_REGION:-us-east-1}"

for arg in "$@"; do
  case $arg in
    --skip-migrate) SKIP_MIGRATE=true ;;
  esac
done

# ── Resolve prefix from branch ──
# Only feature/bug/hotfix branches with wo-{number} get isolated stacks.
# All other branches (main, master, etc.) use the bare "wo" prefix.
if [ -z "${PREFIX:-}" ]; then
  BRANCH=$(git branch --show-current 2>/dev/null || echo "main")
  NUMBER=$(echo "$BRANCH" | sed -n 's/^\(feature\|bug\|hotfix\)\/wo-\([0-9]*\).*/\2/p')
  if [ -n "$NUMBER" ]; then
    PREFIX="wo-${NUMBER}"
  else
    PREFIX="wo"
  fi
fi

STACK_NAME="${PREFIX}-${STAGE}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$INFRA_DIR")"

echo "═══════════════════════════════════════════════"
echo "  Workflow Orchestrator — Deploy"
echo "═══════════════════════════════════════════════"
echo ""
echo "  Prefix:  ${PREFIX}"
echo "  Stage:   ${STAGE}"
echo "  Stack:   ${STACK_NAME}"
echo ""

# ── 1. Verify AWS credentials ──
echo "→ Checking AWS credentials..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || {
  echo "✗ AWS credentials not configured. Run: aws configure sso"
  exit 1
}
echo "  Account: ${ACCOUNT_ID}  Region: ${AWS_REGION}"

# ── 2. Get ECR repo URI ──
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PREFIX}-app"

# ── 3. Build and push Docker image ──
echo ""
echo "→ Building Docker image..."
cd "$PROJECT_ROOT"
docker build --target production -t "${PREFIX}-app:latest" .

echo "→ Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "→ Tagging and pushing image..."
IMAGE_TAG="$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
docker tag "${PREFIX}-app:latest" "${ECR_REPO}:latest"
docker tag "${PREFIX}-app:latest" "${ECR_REPO}:${IMAGE_TAG}"
docker push "${ECR_REPO}:latest"
docker push "${ECR_REPO}:${IMAGE_TAG}"
echo "  Pushed: ${ECR_REPO}:${IMAGE_TAG}"

# ── 4. Deploy CDK stack ──
echo ""
echo "→ Deploying CDK stack..."
cd "$INFRA_DIR"
STAGE="${STAGE}" PREFIX="${PREFIX}" npx cdk deploy "${STACK_NAME}" \
  --require-approval never \
  --outputs-file "cdk-${STAGE}-outputs.json"

echo "  Stack deployed successfully."

# ── 5. Run Alembic migration ──
if [ "$SKIP_MIGRATE" = false ]; then
  echo ""
  echo "→ Running database migration..."

  CLUSTER_NAME=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?ExportName=='${PREFIX}-cluster-name'].OutputValue" \
    --output text)

  MIGRATION_TASK_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?ExportName=='${PREFIX}-migration-task-arn'].OutputValue" \
    --output text)

  SUBNETS=$(aws ec2 describe-subnets \
    --filters "Name=tag:Name,Values=*${PREFIX}*" \
    --query "Subnets[].SubnetId" --output text | tr '\t' ',')

  ECS_SG=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=${PREFIX}-ecs-sg" \
    --query "SecurityGroups[0].GroupId" --output text)

  TASK_ARN=$(aws ecs run-task \
    --cluster "${CLUSTER_NAME}" \
    --task-definition "${MIGRATION_TASK_ARN}" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS}],securityGroups=[${ECS_SG}],assignPublicIp=ENABLED}" \
    --query "tasks[0].taskArn" --output text)

  echo "  Migration task started: ${TASK_ARN}"
  echo "  Waiting for completion..."

  aws ecs wait tasks-stopped --cluster "${CLUSTER_NAME}" --tasks "${TASK_ARN}"

  EXIT_CODE=$(aws ecs describe-tasks \
    --cluster "${CLUSTER_NAME}" \
    --tasks "${TASK_ARN}" \
    --query "tasks[0].containers[0].exitCode" --output text)

  if [ "$EXIT_CODE" = "0" ]; then
    echo "  ✓ Migration completed successfully."
  else
    echo "  ✗ Migration failed (exit code: ${EXIT_CODE})."
    echo "    Check logs: aws logs tail /ecs/${PREFIX}/migration --follow"
    exit 1
  fi
fi

# ── 6. Force new deployments to pick up latest image ──
echo ""
echo "→ Forcing new deployments..."
for SERVICE in api worker orchestrator reaper; do
  aws ecs update-service \
    --cluster "${CLUSTER_NAME:-$(aws cloudformation describe-stacks \
      --stack-name "${STACK_NAME}" \
      --query "Stacks[0].Outputs[?ExportName=='${PREFIX}-cluster-name'].OutputValue" \
      --output text)}" \
    --service "${PREFIX}-${SERVICE}" \
    --force-new-deployment \
    --no-cli-pager > /dev/null 2>&1
  echo "  ✓ ${SERVICE} redeploying"
done

# ── 7. Summary ──
echo ""
echo "═══════════════════════════════════════════════"
echo "  ✓ Deployment complete!"
echo ""

API_URL=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?ExportName=='${PREFIX}-api-url'].OutputValue" \
  --output text 2>/dev/null || echo "pending")

echo "  API URL:      ${API_URL}"
echo "  ECR Image:    ${ECR_REPO}:${IMAGE_TAG}"
echo "  Prefix:       ${PREFIX}"
echo "  Stage:        ${STAGE}"
echo "  Stack:        ${STACK_NAME}"
echo ""
echo "  View logs:    aws logs tail /ecs/${PREFIX}/api --follow"
echo "  Health check: curl ${API_URL}/health"
echo "═══════════════════════════════════════════════"
