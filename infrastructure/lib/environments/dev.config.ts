import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { EnvironmentConfig } from '../config.js';

export const devConfig: EnvironmentConfig = {
    stage: 'dev',

    apiCpu: 256,
    apiMemoryMiB: 512,
    apiDesiredCount: 1,
    workerCpu: 256,
    workerMemoryMiB: 512,
    workerDesiredCount: 1,
    orchestratorCpu: 256,
    orchestratorMemoryMiB: 512,
    orchestratorDesiredCount: 1,
    reaperCpu: 256,
    reaperMemoryMiB: 512,
    reaperDesiredCount: 1,
    useFargateSpot: true,

    dbInstanceClass: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
    dbAllocatedStorageGiB: 20,
    dbMultiAz: false,
    dbBackupRetentionDays: 1,
    dbDeletionProtection: false,

    cacheNodeType: 'cache.t3.micro',
    cacheNumNodes: 1,

    maxAzs: 2,
    natGateways: 0,

    enableAlarms: false,
};
