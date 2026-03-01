import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { EnvironmentConfig } from './config.js';
import { NetworkingConstruct } from './constructs/networking.js';
import { DatabaseConstruct } from './constructs/database.js';
import { CacheConstruct } from './constructs/cache.js';
import { ClusterConstruct } from './constructs/cluster.js';
import { ApiServiceConstruct } from './constructs/api-service.js';
import { BackgroundServiceConstruct } from './constructs/background-service.js';
import { MonitoringConstruct } from './constructs/monitoring.js';
import { applyCommonTags } from './utils/index.js';

interface WorkflowStackProps extends cdk.StackProps {
  readonly prefix: string;
  readonly config: EnvironmentConfig;
}

// Root stack that wires all constructs together. Each construct is self-contained
// and independently configurable through EnvironmentConfig. The prefix ensures
// every resource name is unique, enabling multiple stacks per AWS account.
export class WorkflowStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: WorkflowStackProps) {
    super(scope, id, props);

    const { prefix, config } = props;

    // ──── 1. Networking ────
    const network = new NetworkingConstruct(this, 'Network', {
      prefix,
      stage: config.stage,
      maxAzs: config.maxAzs,
      natGateways: config.natGateways,
    });

    // ──── 2. Database (RDS PostgreSQL) ────
    // Stores workflow definitions, execution history, and audit trails.
    // Hot-path state (active task status, locks) lives in Redis instead.
    const database = new DatabaseConstruct(this, 'Database', {
      prefix,
      stage: config.stage,
      vpc: network.vpc,
      securityGroup: network.dbSecurityGroup,
      instanceType: config.dbInstanceClass,
      allocatedStorageGiB: config.dbAllocatedStorageGiB,
      multiAz: config.dbMultiAz,
      backupRetentionDays: config.dbBackupRetentionDays,
      deletionProtection: config.dbDeletionProtection,
    });

    // ──── 3. Cache (ElastiCache Redis) ────
    // Serves as the message broker (Redis Streams), state store (hashes),
    // distributed lock manager (Redlock), and rate limiter.
    const cache = new CacheConstruct(this, 'Cache', {
      prefix,
      stage: config.stage,
      vpc: network.vpc,
      securityGroup: network.cacheSecurityGroup,
      nodeType: config.cacheNodeType,
      numNodes: config.cacheNumNodes,
    });

    // ──── 4. ECS Cluster + ECR ────
    const cluster = new ClusterConstruct(this, 'Cluster', {
      prefix,
      stage: config.stage,
      vpc: network.vpc,
    });

    // Shared props for all Fargate services — same image, same DB/Redis
    // credentials, same network placement.
    const sharedServiceProps = {
      cluster: cluster.cluster,
      repository: cluster.repository,
      ecsSecurityGroup: network.ecsSecurityGroup,
      ecsSubnets: network.ecsSubnets,
      assignPublicIp: network.assignPublicIp,
      dbSecret: database.secret,
      redisEndpoint: cache.endpoint,
      redisPort: cache.port,
    };

    // ──── 5. API Service (Fargate + ALB) ────
    // FastAPI application exposed via ALB. Handles DAG submission,
    // execution triggers, status queries and DLQ management.
    const apiService = new ApiServiceConstruct(this, 'ApiService', {
      prefix,
      stage: config.stage,
      ...sharedServiceProps,
      vpc: network.vpc,
      albSecurityGroup: network.albSecurityGroup,
      cpu: config.apiCpu,
      memoryMiB: config.apiMemoryMiB,
      desiredCount: config.apiDesiredCount,
    });

    // ──── 6. Worker Service ────
    // Consumes tasks from Redis Streams, executes task handlers with
    // retry + circuit breaker, and publishes completion events.
    const workerService = new BackgroundServiceConstruct(this, 'WorkerService', {
      prefix,
      stage: config.stage,
      serviceName: 'worker',
      command: ['python', '-m', 'src.worker'],
      ...sharedServiceProps,
      cpu: config.workerCpu,
      memoryMiB: config.workerMemoryMiB,
      desiredCount: config.workerDesiredCount,
      useFargateSpot: config.useFargateSpot,
    });

    // ──── 7. Orchestrator Service ────
    // Listens for task completion events, resolves DAG dependencies,
    // and dispatches newly-ready tasks. Uses distributed locks to
    // handle fan-in (multiple completions enabling the same downstream task).
    const orchestratorService = new BackgroundServiceConstruct(
      this,
      'OrchestratorService',
      {
        prefix,
        stage: config.stage,
        serviceName: 'orchestrator',
        command: ['python', '-m', 'src.orchestrator'],
        ...sharedServiceProps,
        cpu: config.orchestratorCpu,
        memoryMiB: config.orchestratorMemoryMiB,
        desiredCount: config.orchestratorDesiredCount,
        useFargateSpot: config.useFargateSpot,
      },
    );

    // ──── 8. Reaper Service ────
    // Scans the Redis Streams PEL (Pending Entries List) for tasks claimed
    // by stalled consumers and re-queues them via XAUTOCLAIM.
    const reaperService = new BackgroundServiceConstruct(
      this,
      'ReaperService',
      {
        prefix,
        stage: config.stage,
        serviceName: 'reaper',
        command: ['python', '-m', 'src.adapters.secondary.workers.reaper'],
        ...sharedServiceProps,
        cpu: config.reaperCpu,
        memoryMiB: config.reaperMemoryMiB,
        desiredCount: config.reaperDesiredCount,
        useFargateSpot: config.useFargateSpot,
      },
    );

    // ──── 9. Monitoring ────
    new MonitoringConstruct(this, 'Monitoring', {
      prefix,
      stage: config.stage,
      enableAlarms: config.enableAlarms,
      alarmEmailEndpoint: config.alarmEmailEndpoint,
      apiService: apiService.service,
      workerService: workerService.service,
      orchestratorService: orchestratorService.service,
      reaperService: reaperService.service,
      dbInstance: database.instance,
    });

    // ──── One-off Migration Task ────
    // Separate task definition for running Alembic migrations as a
    // standalone ECS task (not a long-running service). Triggered
    // by deploy.sh or the CI/CD pipeline after each deploy.
    const migrationTaskDef = new cdk.aws_ecs.FargateTaskDefinition(
      this,
      'MigrationTaskDef',
      {
        family: `${prefix}-migration`,
        cpu: 256,
        memoryLimitMiB: 512,
      },
    );

    migrationTaskDef.addContainer('migration', {
      image: cdk.aws_ecs.ContainerImage.fromEcrRepository(
        cluster.repository,
        'latest',
      ),
      command: ['python', '-m', 'alembic', 'upgrade', 'head'],
      logging: cdk.aws_ecs.LogDrivers.awsLogs({
        logGroup: new cdk.aws_logs.LogGroup(this, 'MigrationLogGroup', {
          logGroupName: `/ecs/${prefix}/migration`,
          retention: cdk.aws_logs.RetentionDays.THREE_DAYS,
          removalPolicy: cdk.RemovalPolicy.DESTROY,
        }),
        streamPrefix: 'migration',
      }),
      environment: {
        DB_PORT: '5432',
        DB_NAME: 'workflow',
        REDIS_HOST: cache.endpoint,
        REDIS_PORT: cache.port,
      },
      secrets: {
        DB_HOST: cdk.aws_ecs.Secret.fromSecretsManager(database.secret, 'host'),
        DB_USERNAME: cdk.aws_ecs.Secret.fromSecretsManager(database.secret, 'username'),
        DB_PASSWORD: cdk.aws_ecs.Secret.fromSecretsManager(database.secret, 'password'),
      },
    });

    database.secret.grantRead(migrationTaskDef.taskRole);

    new cdk.CfnOutput(this, 'MigrationTaskDefArn', {
      value: migrationTaskDef.taskDefinitionArn,
      exportName: `${prefix}-migration-task-arn`,
    });

    applyCommonTags(this, { prefix, stage: config.stage, component: 'Stack' });
  }
}
