import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';

interface TagProps {
    readonly prefix: string;
    readonly stage: string;
    readonly component: string;
}

// Applies a consistent set of tags for cost allocation, resource management,
// and quick identification across all stacks and environments.
export function applyCommonTags(scope: Construct, tags: TagProps) {
    cdk.Tags.of(scope).add('Project', 'WorkflowOrchestrator');
    cdk.Tags.of(scope).add('Prefix', tags.prefix);
    cdk.Tags.of(scope).add('Stage', tags.stage);
    cdk.Tags.of(scope).add('Component', tags.component);
    cdk.Tags.of(scope).add('ManagedBy', 'CDK');
}
