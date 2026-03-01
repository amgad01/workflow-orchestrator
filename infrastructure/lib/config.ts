import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { devConfig } from './environments/dev.config.js';
import { prodConfig } from './environments/prod.config.js';

export interface EnvironmentConfig {
  readonly stage: string;

  readonly apiCpu: number;
  readonly apiMemoryMiB: number;
  readonly apiDesiredCount: number;
  readonly workerCpu: number;
  readonly workerMemoryMiB: number;
  readonly workerDesiredCount: number;
  readonly orchestratorCpu: number;
  readonly orchestratorMemoryMiB: number;
  readonly orchestratorDesiredCount: number;
  readonly reaperCpu: number;
  readonly reaperMemoryMiB: number;
  readonly reaperDesiredCount: number;
  readonly useFargateSpot: boolean;

  readonly dbInstanceClass: ec2.InstanceType;
  readonly dbAllocatedStorageGiB: number;
  readonly dbMultiAz: boolean;
  readonly dbBackupRetentionDays: number;
  readonly dbDeletionProtection: boolean;

  readonly cacheNodeType: string;
  readonly cacheNumNodes: number;

  readonly maxAzs: number;
  readonly natGateways: number;

  readonly enableAlarms: boolean;
  readonly alarmEmailEndpoint?: string;
}

export function getConfig(stage: string): EnvironmentConfig {
  switch (stage) {
    case 'prod':
    case 'production':
      return prodConfig;
    case 'dev':
    case 'development':
    default:
      return devConfig;
  }
}
