import { Construct } from 'constructs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as snsSubscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as cw_actions from 'aws-cdk-lib/aws-cloudwatch-actions';
import { applyCommonTags } from '../utils/index.js';

export interface MonitoringProps {
  readonly prefix: string;
  readonly stage: string;
  readonly enableAlarms: boolean;
  readonly alarmEmailEndpoint?: string;
  readonly apiService: ecs.FargateService;
  readonly workerService: ecs.FargateService;
  readonly orchestratorService: ecs.FargateService;
  readonly reaperService: ecs.FargateService;
  readonly dbInstance: rds.DatabaseInstance;
}

export class MonitoringConstruct extends Construct {
  constructor(scope: Construct, id: string, props: MonitoringProps) {
    super(scope, id);

    let alarmTopic: sns.Topic | undefined;
    if (props.enableAlarms) {
      alarmTopic = new sns.Topic(this, 'AlarmTopic', {
        topicName: `${props.prefix}-alarms`,
        displayName: `${props.prefix} Workflow Orchestrator Alarms`,
      });

      if (props.alarmEmailEndpoint) {
        alarmTopic.addSubscription(
          new snsSubscriptions.EmailSubscription(props.alarmEmailEndpoint),
        );
      }
    }

    // Single dashboard for all four services + RDS gives a unified view
    // of the entire system at a glance.
    const dashboard = new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: `${props.prefix}-workflow-orchestrator`,
      periodOverride: cloudwatch.PeriodOverride.AUTO,
    });

    const serviceWidgets = (
      name: string,
      service: ecs.FargateService,
    ): cloudwatch.IWidget[] => [
        new cloudwatch.GraphWidget({
          title: `${name} — CPU & Memory`,
          left: [
            service.metricCpuUtilization({ statistic: 'Average' }),
            service.metricMemoryUtilization({ statistic: 'Average' }),
          ],
          width: 12,
        }),
        new cloudwatch.GraphWidget({
          title: `${name} — Running Tasks`,
          left: [
            new cloudwatch.Metric({
              namespace: 'AWS/ECS',
              metricName: 'RunningTaskCount',
              dimensionsMap: {
                ClusterName: service.cluster.clusterName,
                ServiceName: service.serviceName,
              },
              statistic: 'Average',
            }),
          ],
          width: 12,
        }),
      ];

    dashboard.addWidgets(
      new cloudwatch.TextWidget({
        markdown: `# ${props.prefix} — Workflow Orchestrator`,
        width: 24,
        height: 1,
      }),
    );

    dashboard.addWidgets(...serviceWidgets('API', props.apiService));
    dashboard.addWidgets(...serviceWidgets('Worker', props.workerService));
    dashboard.addWidgets(
      ...serviceWidgets('Orchestrator', props.orchestratorService),
    );
    dashboard.addWidgets(...serviceWidgets('Reaper', props.reaperService));

    dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: 'RDS — CPU & Connections',
        left: [
          props.dbInstance.metricCPUUtilization({ statistic: 'Average' }),
          props.dbInstance.metricDatabaseConnections({ statistic: 'Average' }),
        ],
        width: 12,
      }),
      new cloudwatch.GraphWidget({
        title: 'RDS — Free Storage & IOPS',
        left: [
          props.dbInstance.metricFreeStorageSpace({ statistic: 'Average' }),
          props.dbInstance.metricReadIOPS({ statistic: 'Average' }),
          props.dbInstance.metricWriteIOPS({ statistic: 'Average' }),
        ],
        width: 12,
      }),
    );

    // Alarms are opt-in (disabled for dev to avoid SNS costs).
    // Thresholds are conservative — they fire before user impact,
    // not after.
    if (props.enableAlarms && alarmTopic) {
      const addAlarm = (
        name: string,
        metric: cloudwatch.Metric,
        threshold: number,
        comparisonOperator: cloudwatch.ComparisonOperator,
        evaluationPeriods: number = 2,
      ) => {
        const alarm = new cloudwatch.Alarm(this, name, {
          alarmName: `${props.prefix}-${name}`,
          metric,
          threshold,
          comparisonOperator,
          evaluationPeriods,
          treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
        });
        alarm.addAlarmAction(new cw_actions.SnsAction(alarmTopic));
        alarm.addOkAction(new cw_actions.SnsAction(alarmTopic));
      };

      addAlarm(
        'ApiHighCpu',
        props.apiService.metricCpuUtilization({ statistic: 'Average' }),
        80,
        cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      );

      addAlarm(
        'DbHighCpu',
        props.dbInstance.metricCPUUtilization({ statistic: 'Average' }),
        80,
        cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      );

      // 2 GB free storage is a critical threshold — below this, Postgres
      // may reject writes.
      addAlarm(
        'DbLowStorage',
        props.dbInstance.metricFreeStorageSpace({ statistic: 'Average' }),
        2 * 1024 * 1024 * 1024,
        cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
      );

      addAlarm(
        'DbHighConnections',
        props.dbInstance.metricDatabaseConnections({ statistic: 'Average' }),
        50,
        cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      );
    }

    applyCommonTags(this, { prefix: props.prefix, stage: props.stage, component: 'Monitoring' });
  }
}
