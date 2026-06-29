import React from 'react';
import CodeBlock from './CodeBlock';
import ConfigSamplerClient, {
  ConfigTabId,
  KnobRow,
  KNOBS,
} from './ConfigSamplerClient';

export type { ConfigTabId, KnobRow };
export { KNOBS };

/**
 * Properties for the ConfigSampler component.
 */
export interface ConfigSamplerProps {
  /** The initially active tab ID. Defaults to 'minimal'. */
  defaultTab?: ConfigTabId;
}

/**
 * Verbatim text content for the minimal configuration YAML file.
 */
export const MINIMAL_YAML = `# .lychee.yml — minimal
model:
  default: claude-sonnet-4-6

review:
  severity_threshold: info

features:
  cost_footer: true`;

/**
 * Verbatim text content for the full-featured configuration YAML file.
 */
export const FULL_YAML = `model:
  default: claude-sonnet-4-6
  triage: claude-haiku-4-5-20251001
  large_pr: claude-opus-4-8

review:
  ignore_globs:
    - "**/*.lock"
    - "**/*.min.js"
    - "vendor/**"
  severity_threshold: info
  tone: balanced
  language: en
  budget_cap_usd: 0.50

features:
  inline_comments: true
  cost_footer: true
  commands: true
  triage_pass: true

conventions_file: .github/conventions.md

authorization:
  allowed_users:
    - alice
    - bob`;

/**
 * Verbatim text content for the monorepo configuration YAML file.
 */
export const MONOREPO_YAML = `review:
  scope_rules:
    # Skip generated files entirely
    - paths: ["**/generated/**", "**/*.gen.ts"]
      ignore: true

    # Detailed review for security-sensitive code
    - paths: ["src/auth/**", "src/crypto/**"]
      tone: detailed
      severity_threshold: info

    # Use Opus for infrastructure changes
    - paths: ["terraform/**", "k8s/**"]
      labels: ["infrastructure"]
      model: claude-opus-4-8

    # Concise reviews for documentation PRs
    - labels: ["docs"]
      tone: concise
      severity_threshold: major`;

/**
 * Server component wrapper that pre-renders configuration code blocks
 * on the server, and passes the resulting elements to the client component.
 *
 * @param props - Props containing active tab setting override.
 * @returns The pre-rendered server wrapper component structure.
 */
export default function ConfigSampler({
  defaultTab = 'minimal',
}: ConfigSamplerProps): JSX.Element {
  // Pre-render YAML code blocks. CodeBlock is an async server component.
  const minimalPanel = (
    <CodeBlock code={MINIMAL_YAML} lang="yaml" filename=".lychee.yml" />
  );
  const fullPanel = (
    <CodeBlock code={FULL_YAML} lang="yaml" />
  );
  const monorepoPanel = (
    <CodeBlock code={MONOREPO_YAML} lang="yaml" />
  );

  return (
    <ConfigSamplerClient
      defaultTab={defaultTab}
      minimalPanel={minimalPanel}
      fullPanel={fullPanel}
      monorepoPanel={monorepoPanel}
    />
  );
}
