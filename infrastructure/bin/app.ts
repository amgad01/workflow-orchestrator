#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { WorkflowStack } from '../lib/workflow-stack.js';
import { getConfig } from '../lib/config.js';
import { resolvePrefix } from '../lib/utils/index.js';

const app = new cdk.App();

const stage = process.env.STAGE ?? app.node.tryGetContext('stage') ?? 'dev';
const prefix = resolvePrefix();
const config = getConfig(stage);

// Stack ID = "${prefix}-${stage}" (e.g., "wo-dev", "wo-42-dev")
// This naming enables isolated per-branch deployments in the same account.
new WorkflowStack(app, `${prefix}-${stage}`, {
  prefix,
  config,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'us-east-1',
  },
  description: `Workflow Orchestrator — ${prefix} (${stage})`,
});

app.synth();
