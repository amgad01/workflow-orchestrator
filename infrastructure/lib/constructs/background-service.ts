import { Construct } from 'constructs';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as cdk from 'aws-cdk-lib';
import { applyCommonTags } from '../utils/index.js';

export interface BackgroundServiceProps {
  readonly prefix: string;
  readonly stage: string;
  readonly serviceName: string;
  readonly command: string[];
  readonly cluster: ecs.ICluster;
  readonly repository: ecr.IRepository;
  readonly ecsSecurityGroup: ec2.SecurityGroup;
  readonly ecsSubnets: ec2.SubnetSelection;
  readonly assignPublicIp: boolean;
  readonly dbSecret: secretsmanager.ISecret;
  readonly redisEndpoint: string;
  readonly redisPort: string;
  readonly cpu: number;
  readonly memoryMiB: number;
  readonly desiredCount: number;
  readonly useFargateSpot: boolean;
  readonly additionalEnv?: Record<string, string>;
}

// Reusable Fargate service for internal workloads (worker, orchestrator, reaper).
// These services consume from Redis Streams and have no ALB — they share the
// same container image as the API but run with different entry-point commands.
export class BackgroundServiceConstruct extends Construct {
  public readonly service: ecs.FargateService;

  constructor(scope: Construct, id: string, props: BackgroundServiceProps) {
    super(scope, id);

    const fullName = `${props.prefix}-${props.serviceName}`;

    const taskDef = new ecs.FargateTaskDefinition(this, 'TaskDef', {
      family: fullName,
      cpu: props.cpu,
      memoryLimitMiB: props.memoryMiB,
    });

    const logGroup = new logs.LogGroup(this, 'LogGroup', {
      logGroupName: `/ecs/${props.prefix}/${props.serviceName}`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    taskDef.addContainer(props.serviceName, {
      image: ecs.ContainerImage.fromEcrRepository(props.repository, 'latest'),
      command: props.command,
      logging: ecs.LogDrivers.awsLogs({
        logGroup,
        streamPrefix: props.serviceName,
      }),
      environment: {
        APP_NAME: 'Workflow Orchestrator',
        DB_PORT: '5432',
        DB_NAME: 'workflow',
        REDIS_PORT: props.redisPort,
        REDIS_HOST: props.redisEndpoint,
        WORKER_ENABLE_DELAYS: 'false',
        ...props.additionalEnv,
      },
      secrets: {
        DB_HOST: ecs.Secret.fromSecretsManager(props.dbSecret, 'host'),
        DB_USERNAME: ecs.Secret.fromSecretsManager(props.dbSecret, 'username'),
        DB_PASSWORD: ecs.Secret.fromSecretsManager(props.dbSecret, 'password'),
      },
    });

    // Fargate Spot provides up to 70% cost savings for background workers.
    // Acceptable for dev because these services are stateless and Redis Streams
    // consumer groups handle rebalancing when a task is interrupted.
    // Prod uses on-demand Fargate for predictable availability.
    const capacityProviderStrategies: ecs.CapacityProviderStrategy[] =
      props.useFargateSpot
        ? [
          { capacityProvider: 'FARGATE_SPOT', weight: 1 },
          { capacityProvider: 'FARGATE', weight: 0, base: 0 },
        ]
        : [{ capacityProvider: 'FARGATE', weight: 1 }];

    this.service = new ecs.FargateService(this, 'Service', {
      serviceName: fullName,
      cluster: props.cluster,
      taskDefinition: taskDef,
      desiredCount: props.desiredCount,
      securityGroups: [props.ecsSecurityGroup],
      vpcSubnets: props.ecsSubnets,
      assignPublicIp: props.assignPublicIp,
      capacityProviderStrategies,
      circuitBreaker: { enable: true, rollback: true },
      enableExecuteCommand: true,
    });

    applyCommonTags(this, { prefix: props.prefix, stage: props.stage, component: props.serviceName });
  }
}
