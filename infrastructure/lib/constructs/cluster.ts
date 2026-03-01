import { Construct } from 'constructs';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { applyCommonTags } from '../utils/index.js';

export interface ClusterProps {
  readonly prefix: string;
  readonly stage: string;
  readonly vpc: ec2.IVpc;
}

export class ClusterConstruct extends Construct {
  public readonly cluster: ecs.Cluster;
  public readonly repository: ecr.Repository;

  constructor(scope: Construct, id: string, props: ClusterProps) {
    super(scope, id);

    this.cluster = new ecs.Cluster(this, 'Cluster', {
      clusterName: `${props.prefix}-cluster`,
      vpc: props.vpc,
      // Container Insights costs ~$0.50/task/month. Disabled by default;
      // enable in prod.config.ts if needed.
      containerInsights: false,
    });

    this.repository = new ecr.Repository(this, 'Repo', {
      repositoryName: `${props.prefix}-app`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      emptyOnDelete: true,
      // ECR free tier covers 500 MB. Keeping only 5 images avoids surprise
      // charges and simplifies rollback (latest 5 deploys).
      lifecycleRules: [
        {
          maxImageCount: 5,
          description: 'Keep last 5 images only',
        },
      ],
    });

    new cdk.CfnOutput(this, 'EcrRepoUri', {
      value: this.repository.repositoryUri,
      exportName: `${props.prefix}-ecr-uri`,
    });

    new cdk.CfnOutput(this, 'ClusterName', {
      value: this.cluster.clusterName,
      exportName: `${props.prefix}-cluster-name`,
    });

    applyCommonTags(this, { prefix: props.prefix, stage: props.stage, component: 'Compute' });
  }
}
