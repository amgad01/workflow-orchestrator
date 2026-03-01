import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { EnvironmentConfig } from '../config.js';

export const prodConfig: EnvironmentConfig = {
    stage: 'prod',

    apiCpu: 512,
    apiMemoryMiB: 1024,
    apiDesiredCount: 2,
    workerCpu: 512,
    workerMemoryMiB: 1024,
    workerDesiredCount: 3,
    orchestratorCpu: 512,
    orchestratorMemoryMiB: 1024,
    orchestratorDesiredCount: 2,
    reaperCpu: 256,
    reaperMemoryMiB: 512,
    reaperDesiredCount: 1,
    useFargateSpot: false,

    dbInstanceClass: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
    dbAllocatedStorageGiB: 50,
    dbMultiAz: true,
    dbBackupRetentionDays: 7,
    dbDeletionProtection: true,

    cacheNodeType: 'cache.t3.small',
    cacheNumNodes: 1,

    maxAzs: 2,
    natGateways: 1,

    enableAlarms: true,
    alarmEmailEndpoint: undefined,
};
