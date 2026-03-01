import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as elasticache from 'aws-cdk-lib/aws-elasticache';
import * as cdk from 'aws-cdk-lib';
import { applyCommonTags } from '../utils/index.js';

export interface CacheProps {
  readonly prefix: string;
  readonly stage: string;
  readonly vpc: ec2.IVpc;
  readonly securityGroup: ec2.SecurityGroup;
  readonly nodeType: string;
  readonly numNodes: number;
}

export class CacheConstruct extends Construct {
  public readonly endpoint: string;
  public readonly port: string;

  constructor(scope: Construct, id: string, props: CacheProps) {
    super(scope, id);

    const subnetGroup = new elasticache.CfnSubnetGroup(this, 'SubnetGroup', {
      cacheSubnetGroupName: `${props.prefix}-redis-subnets`,
      description: `Redis subnet group for ${props.prefix}`,
      subnetIds: props.vpc.publicSubnets.map((s) => s.subnetId),
    });

    // AOF (Append-Only File) is critical for Redis Streams durability.
    // Without it, a Redis restart would lose all pending stream messages
    // (task dispatches, completion events). noeviction policy prevents
    // Redis from silently dropping stream entries under memory pressure.
    const parameterGroup = new elasticache.CfnParameterGroup(
      this,
      'ParamGroup',
      {
        cacheParameterGroupFamily: 'redis7',
        description: `Redis 7 params for ${props.prefix}`,
        properties: {
          'appendonly': 'yes',
          'appendfsync': 'everysec',
          'maxmemory-policy': 'noeviction',
        },
      },
    );

    const cluster = new elasticache.CfnCacheCluster(this, 'Redis', {
      clusterName: `${props.prefix}-redis`,
      engine: 'redis',
      engineVersion: '7.1',
      cacheNodeType: props.nodeType,
      numCacheNodes: props.numNodes,
      cacheSubnetGroupName: subnetGroup.cacheSubnetGroupName,
      cacheParameterGroupName: parameterGroup.ref,
      vpcSecurityGroupIds: [props.securityGroup.securityGroupId],
      port: 6379,
    });

    cluster.addDependency(subnetGroup);
    cluster.addDependency(parameterGroup);

    this.endpoint = cluster.attrRedisEndpointAddress;
    this.port = cluster.attrRedisEndpointPort;

    new cdk.CfnOutput(this, 'RedisEndpoint', {
      value: this.endpoint,
      exportName: `${props.prefix}-redis-endpoint`,
    });

    applyCommonTags(this, { prefix: props.prefix, stage: props.stage, component: 'Cache' });
  }
}
