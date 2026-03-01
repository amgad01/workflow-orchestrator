#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# destroy.sh — Tear down the Workflow Orchestrator stack.
#
# Usage:
#   STAGE=dev ./scripts/destroy.sh
#   PREFIX=wo-42 STAGE=dev ./scripts/destroy.sh
# ──────────────────────────────────────────────────────────────
set -euo pipefail

STAGE="${STAGE:-dev}"

# Resolve prefix from branch (mirrors deploy.sh logic)
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

echo "═══════════════════════════════════════════════"
echo "  Workflow Orchestrator — DESTROY"
echo "═══════════════════════════════════════════════"
echo ""
echo "  This will permanently delete ALL resources in stack: ${STACK_NAME}"
echo "  Prefix: ${PREFIX}  Stage: ${STAGE}"
echo ""

read -rp "  Are you sure? (type 'yes' to confirm): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "  Aborted."
  exit 0
fi

echo ""
echo "→ Destroying CDK stack..."
cd "$(dirname "${BASH_SOURCE[0]}")/.."
STAGE="${STAGE}" PREFIX="${PREFIX}" npx cdk destroy "${STACK_NAME}" --force

echo ""
echo "  ✓ Stack ${STACK_NAME} destroyed."
