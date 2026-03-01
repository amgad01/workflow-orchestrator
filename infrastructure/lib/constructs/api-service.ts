import { Construct } from 'constructs';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as cdk from 'aws-cdk-lib';
import { applyCommonTags } from '../utils/index.js';

export interface ApiServiceProps {
  readonly prefix: string;
  readonly stage: string;
  readonly cluster: ecs.ICluster;
  readonly repository: ecr.IRepository;
  readonly vpc: ec2.IVpc;
  readonly ecsSecurityGroup: ec2.SecurityGroup;
  readonly albSecurityGroup: ec2.SecurityGroup;
  readonly ecsSubnets: ec2.SubnetSelection;
  readonly assignPublicIp: boolean;
  readonly dbSecret: secretsmanager.ISecret;
  readonly redisEndpoint: string;
  readonly redisPort: string;
  readonly cpu: number;
  readonly memoryMiB: number;
  readonly desiredCount: number;
}

export class ApiServiceConstruct extends Construct {
  public readonly service: ecs.FargateService;
  public readonly loadBalancer: elbv2.ApplicationLoadBalancer;
  public readonly apiUrl: string;

  constructor(scope: Construct, id: string, props: ApiServiceProps) {
    super(scope, id);

    const taskDef = new ecs.FargateTaskDefinition(this, 'TaskDef', {
      family: `${props.prefix}-api`,
      cpu: props.cpu,
      memoryLimitMiB: props.memoryMiB,
    });

    const logGroup = new logs.LogGroup(this, 'LogGroup', {
      logGroupName: `/ecs/${props.prefix}/api`,
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    const container = taskDef.addContainer('api', {
      image: ecs.ContainerImage.fromEcrRepository(props.repository, 'latest'),
      command: [
        'uvicorn',
        'src.main:app',
        '--host',
        '0.0.0.0',
        '--port',
        '8000',
      ],
      logging: ecs.LogDrivers.awsLogs({
        logGroup,
        streamPrefix: 'api',
      }),
      environment: {
        APP_NAME: 'Workflow Orchestrator',
        DB_PORT: '5432',
        DB_NAME: 'workflow',
        REDIS_PORT: props.redisPort,
        REDIS_HOST: props.redisEndpoint,
        // Workers have configurable delays between tasks. Disabled
        // in ECS because latency is already handled by Redis Streams
        // consumer group blocking reads (XREADGROUP BLOCK).
        WORKER_ENABLE_DELAYS: 'false',
      },
      // DB credentials injected from Secrets Manager — Fargate resolves
      // them at container start, so the secret ARN is the only value
      // baked into the task definition.
      secrets: {
        DB_HOST: ecs.Secret.fromSecretsManager(props.dbSecret, 'host'),
        DB_USERNAME: ecs.Secret.fromSecretsManager(props.dbSecret, 'username'),
        DB_PASSWORD: ecs.Secret.fromSecretsManager(props.dbSecret, 'password'),
      },
      healthCheck: {
        command: [
          'CMD-SHELL',
          'curl -f http://localhost:8000/health || exit 1',
        ],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(10),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
    });

    container.addPortMappings({ containerPort: 8000, protocol: ecs.Protocol.TCP });

    this.loadBalancer = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      loadBalancerName: `${props.prefix}-alb`,
      vpc: props.vpc,
      internetFacing: true,
      securityGroup: props.albSecurityGroup,
    });

    const listener = this.loadBalancer.addListener('HttpListener', {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
    });

    this.service = new ecs.FargateService(this, 'Service', {
      serviceName: `${props.prefix}-api`,
      cluster: props.cluster,
      taskDefinition: taskDef,
      desiredCount: props.desiredCount,
      securityGroups: [props.ecsSecurityGroup],
      vpcSubnets: props.ecsSubnets,
      assignPublicIp: props.assignPublicIp,
      // ECS deployment circuit breaker: rolls back automatically if new
      // tasks fail to stabilize, preventing a bad deploy from killing
      // the entire service.
      circuitBreaker: { enable: true, rollback: true },
      enableExecuteCommand: true,
    });

    listener.addTargets('ApiTarget', {
      port: 8000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [this.service],
      healthCheck: {
        path: '/health',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3,
        healthyHttpCodes: '200',
      },
      // Short deregistration delay keeps deploys fast. The API is
      // stateless so in-flight requests can safely fail over.
      deregistrationDelay: cdk.Duration.seconds(30),
    });

    this.apiUrl = `http://${this.loadBalancer.loadBalancerDnsName}`;

    new cdk.CfnOutput(this, 'ApiEndpoint', {
      value: this.apiUrl,
      exportName: `${props.prefix}-api-url`,
    });

    new cdk.CfnOutput(this, 'AlbDns', {
      value: this.loadBalancer.loadBalancerDnsName,
      exportName: `${props.prefix}-alb-dns`,
    });

    applyCommonTags(this, { prefix: props.prefix, stage: props.stage, component: 'ApiService' });
  }
}
