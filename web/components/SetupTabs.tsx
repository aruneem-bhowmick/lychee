import React from 'react';
import Link from 'next/link';
import CodeBlock from './CodeBlock';
import SetupTabsClient, { SetupTabId } from './SetupTabsClient';
import styles from './SetupTabs.module.css';

// We use the "server wrapper" approach: SetupTabs is a Server Component that composes
// the highlighted CodeBlocks and HTML markup into panels, and passes them to SetupTabsClient
// which handles the 'use client' tab switching and ARIA logic.

export interface SetupTabsProps {
  defaultTab?: SetupTabId;
}

export const WORKFLOW_YAML = `name: Lychee PR Review

on:
  pull_request:
    types: [opened, synchronize, reopened]
  issue_comment:
    types: [created]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    if: >-
      (github.event_name == 'pull_request' &&
       github.event.pull_request.head.repo.full_name == github.repository &&
       secrets.ANTHROPIC_API_KEY != '') ||
      (github.event_name == 'issue_comment' &&
       github.event.issue.pull_request &&
       contains(github.event.comment.body, '@lychee') &&
       secrets.ANTHROPIC_API_KEY != '')
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e .
      - run: python scripts/run_action.py
        env:
          GITHUB_TOKEN: \${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_KEY: \${{ secrets.ANTHROPIC_API_KEY }}`;

export const LYCHEE_YML = `# .lychee.yml (optional — all defaults are sensible)
model:
  default: claude-sonnet-4-6

review:
  severity_threshold: info
  tone: balanced

features:
  cost_footer: true`;

export const DOCKER_BASH = `docker build -t lychee .
docker run -d \\
  -p 8000:8000 \\
  -e LYCHEE_WEBHOOK_SECRET="your-secret" \\
  -e LYCHEE_APP_ID="12345" \\
  -e LYCHEE_PRIVATE_KEY_PATH="/app/private-key.pem" \\
  -e ANTHROPIC_API_KEY="sk-ant-..." \\
  -v /path/to/private-key.pem:/app/private-key.pem:ro \\
  -v /path/to/data:/app/data \\
  lychee`;

export const DIRECT_BASH = `export LYCHEE_WEBHOOK_SECRET="..."
export LYCHEE_APP_ID="..."
export LYCHEE_PRIVATE_KEY_PATH="/path/to/private-key.pem"
export ANTHROPIC_API_KEY="sk-ant-..."

python -m scripts.run_server`;

export const PREREQS_TEXT = `- Python 3.11+
- An Anthropic API key  →  console.anthropic.com`;

export const APP_REGISTER_TEXT = `github.com/settings/apps/new

Required permissions:
  Repository → Contents: Read
  Repository → Pull requests: Read & Write
  Repository → Issues: Read & Write

Subscribe to events:
  Pull request
  Issue comment

Webhook URL: https://<your-host>:8000/webhook`;

export default function SetupTabs({ defaultTab = 'github-actions' }: SetupTabsProps) {
  const actionsPanel = (
    <div className={styles.steps}>
      <div className={styles.step}>
        <h3>Step 1: Prerequisites</h3>
        <CodeBlock code={PREREQS_TEXT} lang="text" />
        <p className={styles.note}>
          Get your key at{' '}
          <a href="https://console.anthropic.com" target="_blank" rel="noopener noreferrer">
            https://console.anthropic.com
          </a>
        </p>
      </div>

      <div className={styles.step}>
        <h3>Step 2: Add the workflow file</h3>
        <p>Create <code>.github/workflows/lychee-review.yml</code>:</p>
        <CodeBlock code={WORKFLOW_YAML} lang="yaml" filename=".github/workflows/lychee-review.yml" />
        <p className={styles.note}>
          GITHUB_TOKEN is provided automatically; ANTHROPIC_API_KEY is the only secret to configure.
        </p>
      </div>

      <div className={styles.step}>
        <h3>Step 3: Add the repository secret</h3>
        <blockquote className={styles.callout}>
          In your GitHub repository: <strong>Settings → Secrets and variables → Actions → New repository secret</strong><br />
          Name: <code>ANTHROPIC_API_KEY</code> / Value: your Anthropic API key
        </blockquote>
      </div>

      <div className={styles.step}>
        <h3>Step 4: Optional — add a .lychee.yml</h3>
        <details className={styles.details}>
          <summary>Optional — add a .lychee.yml</summary>
          <div className={styles.detailsContent}>
            <CodeBlock code={LYCHEE_YML} lang="yaml" filename=".lychee.yml" />
            <p className={styles.note}>
              Lychee runs with all defaults if this file is absent. See the full{' '}
              <Link href="/docs/configuration">Configuration reference</Link> for all options.
            </p>
          </div>
        </details>
      </div>

      <div className={styles.step}>
        <h3>Step 5: Open a pull request</h3>
        <blockquote className={styles.callout}>
          Open or push to any PR in your repository. Lychee will post a review comment automatically.
        </blockquote>
        <a href="#output" className={styles.cta}>
          See what the output looks like →
        </a>
      </div>
    </div>
  );

  const appPanel = (
    <div className={styles.steps}>
      <div className={styles.step}>
        <h3>Step 1: Register a GitHub App</h3>
        <CodeBlock code={APP_REGISTER_TEXT} lang="text" />
        <p className={styles.note}>
          Note the App ID and generate a private key (PEM) after creation.
        </p>
      </div>

      <div className={styles.step}>
        <h3>Step 2: Configure environment variables</h3>
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Variable</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><code>LYCHEE_WEBHOOK_SECRET</code></td>
                <td>Webhook secret from App settings</td>
              </tr>
              <tr>
                <td><code>LYCHEE_APP_ID</code></td>
                <td>GitHub App ID</td>
              </tr>
              <tr>
                <td><code>LYCHEE_PRIVATE_KEY_PATH</code></td>
                <td>Path to your PEM private key file</td>
              </tr>
              <tr>
                <td><code>ANTHROPIC_API_KEY</code></td>
                <td>Anthropic API key</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className={styles.step}>
        <h3>Step 3: Deploy with Docker</h3>
        <CodeBlock code={DOCKER_BASH} lang="bash" />
        <p className={styles.note}>
          <i>The container exposes port 8000 and includes a built-in health check at GET /health.</i>
        </p>
      </div>

      <div className={styles.step}>
        <h3>Step 4: Or run directly</h3>
        <CodeBlock code={DIRECT_BASH} lang="bash" />
      </div>

      <div className={styles.step}>
        <h3>Step 5: Install the App on your repositories</h3>
        <p>After deploying, install the GitHub App on the repositories you want to review.</p>
        <Link href="/docs/deployment" className={styles.cta}>
          Full deployment guide →
        </Link>
      </div>
    </div>
  );

  return <SetupTabsClient defaultTab={defaultTab} actionsPanel={actionsPanel} appPanel={appPanel} />;
}
