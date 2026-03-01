import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { applyCommonTags } from '../utils/index.js';

export interface NetworkingProps {
  readonly prefix: string;
  readonly stage: string;
  readonly maxAzs: number;
  readonly natGateways: number;
}

export class NetworkingConstruct extends Construct {
  public readonly vpc: ec2.IVpc;
  public readonly ecsSecurityGroup: ec2.SecurityGroup;
  public readonly dbSecurityGroup: ec2.SecurityGroup;
  public readonly cacheSecurityGroup: ec2.SecurityGroup;
  public readonly albSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: NetworkingProps) {
    super(scope, id);

    // Dev: public subnets only (no NAT = $0/month). ECS tasks get public IPs
    // with security groups restricting access. This is a common cost-saving
    // pattern for non-production workloads.
    // Prod: private subnets + NAT gateway for proper network isolation.
    const subnetConfiguration: ec2.SubnetConfiguration[] =
      props.natGateways > 0
        ? [
          {
            name: `${props.prefix}-public`,
            subnetType: ec2.SubnetType.PUBLIC,
            cidrMask: 24,
          },
          {
            name: `${props.prefix}-private`,
            subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
            cidrMask: 24,
          },
        ]
        : [
          {
            name: `${props.prefix}-public`,
            subnetType: ec2.SubnetType.PUBLIC,
            cidrMask: 24,
          },
        ];

    this.vpc = new ec2.Vpc(this, 'Vpc', {
      vpcName: `${props.prefix}-vpc`,
      maxAzs: props.maxAzs,
      natGateways: props.natGateways,
      subnetConfiguration,
    });

    // Traffic flow: Internet → ALB (80/443) → ECS (8000) → DB (5432) / Redis (6379)
    // Each hop is restricted to the previous layer's security group.
    this.albSecurityGroup = new ec2.SecurityGroup(this, 'AlbSg', {
      vpc: this.vpc,
      securityGroupName: `${props.prefix}-alb-sg`,
      description: 'ALB — allow HTTP/HTTPS from the public',
      allowAllOutbound: true,
    });
    this.albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'HTTP',
    );
    this.albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'HTTPS',
    );

    this.ecsSecurityGroup = new ec2.SecurityGroup(this, 'EcsSg', {
      vpc: this.vpc,
      securityGroupName: `${props.prefix}-ecs-sg`,
      description: 'ECS tasks',
      allowAllOutbound: true,
    });
    this.ecsSecurityGroup.addIngressRule(
      this.albSecurityGroup,
      ec2.Port.tcp(8000),
      'API traffic from ALB',
    );

    // RDS and ElastiCache only accept connections from ECS tasks — never
    // from the public, even in dev where subnets are public.
    this.dbSecurityGroup = new ec2.SecurityGroup(this, 'DbSg', {
      vpc: this.vpc,
      securityGroupName: `${props.prefix}-db-sg`,
      description: 'RDS — allow 5432 from ECS tasks only',
      allowAllOutbound: false,
    });
    this.dbSecurityGroup.addIngressRule(
      this.ecsSecurityGroup,
      ec2.Port.tcp(5432),
      'PostgreSQL from ECS tasks',
    );

    this.cacheSecurityGroup = new ec2.SecurityGroup(this, 'CacheSg', {
      vpc: this.vpc,
      securityGroupName: `${props.prefix}-cache-sg`,
      description: 'ElastiCache — allow 6379 from ECS tasks only',
      allowAllOutbound: false,
    });
    this.cacheSecurityGroup.addIngressRule(
      this.ecsSecurityGroup,
      ec2.Port.tcp(6379),
      'Redis from ECS tasks',
    );

    applyCommonTags(this, { prefix: props.prefix, stage: props.stage, component: 'Networking' });
  }

  get ecsSubnets(): ec2.SubnetSelection {
    const hasPrivate = this.vpc.privateSubnets.length > 0;
    return hasPrivate
      ? { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS }
      : { subnetType: ec2.SubnetType.PUBLIC };
  }

  get assignPublicIp(): boolean {
    return this.vpc.privateSubnets.length === 0;
  }
}
