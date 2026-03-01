import { execSync } from 'child_process';

// Default prefix for main/master and unrecognized branches.
// Feature branches get `wo-{number}` for isolated multi-deployment.
const DEFAULT_PREFIX = 'wo';

const BRANCH_PREFIX_PATTERN = /^(?:feature|bug|hotfix)\/wo-(\d+)/;

export function resolvePrefix(): string {
    const envPrefix = process.env.PREFIX;
    if (envPrefix) return envPrefix;

    try {
        const branch = execSync('git branch --show-current', { encoding: 'utf-8' }).trim();
        return extractPrefixFromBranch(branch);
    } catch {
        return DEFAULT_PREFIX;
    }
}

export function extractPrefixFromBranch(branch: string): string {
    if (!branch || branch === 'main' || branch === 'master') {
        return DEFAULT_PREFIX;
    }

    // Only feature/bug/hotfix branches with a wo-{number} pattern get isolation
    const match = branch.match(BRANCH_PREFIX_PATTERN);
    if (match) {
        return `wo-${match[1]}`;
    }

    return DEFAULT_PREFIX;
}
