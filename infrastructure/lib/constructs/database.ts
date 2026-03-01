import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as cdk from 'aws-cdk-lib';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { applyCommonTags } from '../utils/index.js';

export interface DatabaseProps {
  readonly prefix: string;
  readonly stage: string;
  readonly vpc: ec2.IVpc;
  readonly securityGroup: ec2.SecurityGroup;
  readonly instanceType: ec2.InstanceType;
  readonly allocatedStorageGiB: number;
  readonly multiAz: boolean;
  readonly backupRetentionDays: number;
  readonly deletionProtection: boolean;
}

export class DatabaseConstruct extends Construct {
  public readonly instance: rds.DatabaseInstance;
  public readonly secret: secretsmanager.ISecret;

  constructor(scope: Construct, id: string, props: DatabaseProps) {
    super(scope, id);

    // Credentials auto-generated and stored in Secrets Manager.
    // ECS tasks access them via ecs.Secret.fromSecretsManager() — never as
    // plaintext environment variables.
    this.instance = new rds.DatabaseInstance(this, 'Postgres', {
      instanceIdentifier: `${props.prefix}-postgres`,
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_15,
      }),
      instanceType: props.instanceType,
      vpc: props.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroups: [props.securityGroup],
      publiclyAccessible: false,

      credentials: rds.Credentials.fromGeneratedSecret('workflow', {
        secretName: `${props.prefix}/db-credentials`,
      }),
      databaseName: 'workflow',

      allocatedStorage: props.allocatedStorageGiB,
      maxAllocatedStorage: props.allocatedStorageGiB * 2,
      storageType: rds.StorageType.GP2,

      multiAz: props.multiAz,
      backupRetention: cdk.Duration.days(props.backupRetentionDays),
      deletionProtection: props.deletionProtection,
      removalPolicy: props.deletionProtection
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,

      enablePerformanceInsights: false,
      monitoringInterval: cdk.Duration.seconds(0),

      // Log queries exceeding 1s for slow-query analysis
      parameterGroup: new rds.ParameterGroup(this, 'Params', {
        engine: rds.DatabaseInstanceEngine.postgres({
          version: rds.PostgresEngineVersion.VER_15,
        }),
        parameters: {
          log_min_duration_statement: '1000',
        },
      }),
    });

    this.secret = this.instance.secret!;

    new cdk.CfnOutput(this, 'DbEndpoint', {
      value: this.instance.dbInstanceEndpointAddress,
      exportName: `${props.prefix}-db-endpoint`,
    });

    applyCommonTags(this, { prefix: props.prefix, stage: props.stage, component: 'Database' });
  }
}
