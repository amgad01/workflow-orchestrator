# Infrastructure

AWS CDK (TypeScript) infrastructure for the Workflow Orchestrator. Supports **multiple isolated deployments** in the same AWS account via branch-based resource naming.

## Architecture

```
infrastructure/
├── bin/
│   └── app.ts                          ← CDK App entry point
├── lib/
│   ├── config.ts                       ← EnvironmentConfig interface + resolver
│   ├── workflow-stack.ts               ← Root stack wiring all constructs
│   ├── constructs/
│   │   ├── networking.ts               ← VPC, subnets, security groups
│   │   ├── database.ts                 ← RDS PostgreSQL 15
│   │   ├── cache.ts                    ← ElastiCache Redis 7 (AOF enabled)
│   │   ├── cluster.ts                  ← ECS Cluster + ECR repository
│   │   ├── api-service.ts             ← Fargate service + ALB
│   │   ├── background-service.ts      ← Reusable Fargate service (worker, orchestrator, reaper)
│   │   └── monitoring.ts             ← CloudWatch Dashboard + Alarms + SNS
│   ├── environments/
│   │   ├── dev.config.ts               ← Dev: Free Tier optimized
│   │   └── prod.config.ts              ← Prod: Multi-AZ, backups, alarms
│   └── utils/
│       ├── tag.ts                      ← Consistent resource tagging
│       ├── prefix.ts                   ← Branch-based prefix resolution
│       └── index.ts
└── scripts/
    ├── deploy.sh                       ← Build → Push → CDK Deploy → Migrate → Redeploy
    └── destroy.sh                      ← Tear down a stack
```

## Multi-Deployment Isolation

Every deployment is identified by a **prefix** derived from the Git branch name:

| Branch | Prefix | Stack Name |
|---|---|---|
| `main` | `wo` | `wo-dev` |
| `feature/wo-42-add-retries` | `wo-42` | `wo-42-dev` |
| `bug/wo-7-fix-timeout` | `wo-7` | `wo-7-dev` |
| `hotfix/wo-99-critical-patch` | `wo-99` | `wo-99-dev` |

Only `feature/`, `bug/`, and `hotfix/` branches with a `wo-{number}` pattern get isolated stacks. All other branches use the bare `wo` prefix.

**Override manually:**
```bash
PREFIX=wo-99 STAGE=dev ./scripts/deploy.sh
```

## Provisioned Resources

| Resource | Dev (Free Tier) | Prod |
|---|---|---|
| RDS PostgreSQL | `db.t3.micro`, 20 GiB, single-AZ | `db.t3.small`, 50 GiB, Multi-AZ |
| ElastiCache Redis | `cache.t3.micro`, 1 node | `cache.t3.small`, 1 node |
| Fargate Services | 4 × 0.25 vCPU / 0.5 GB (Spot) | 4 × 0.5 vCPU / 1 GB |
| ALB | 1 (internet-facing) | 1 (internet-facing) |
| NAT Gateway | 0 (public subnets only) | 1 |
| CloudWatch Alarms | Disabled | CPU, storage, connections |

## Deploy

```bash
cd infrastructure

# Install dependencies
npm ci

# Deploy (prefix auto-detected from current branch)
STAGE=dev ./scripts/deploy.sh

# Deploy with explicit prefix
PREFIX=wo-42 STAGE=dev ./scripts/deploy.sh

# Deploy without running migrations
STAGE=dev ./scripts/deploy.sh --skip-migrate

# Destroy
STAGE=dev ./scripts/destroy.sh
```

## Prerequisites

- **AWS CLI v2** — configured with valid credentials
- **Docker** — running (for image build + push)
- **CDK Bootstrap** — `npx cdk bootstrap` (one-time per account/region)
- **Node.js 20+** — for CDK synthesis
