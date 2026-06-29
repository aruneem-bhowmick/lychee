import React from 'react';
import Link from 'next/link';
import PipelineDiagram from './PipelineDiagram';
import styles from './HowItWorks.module.css';

/**
 * Represents a single row in the deployment comparison table.
 */
export interface DeploymentRow {
  /** The row label indicating the feature being compared. */
  label: string;
  /** The value for CLI Mode. */
  cli: string;
  /** The value for Server Mode. */
  server: string;
}

/**
 * The rows of the deployment modes comparison table.
 */
export const DEPLOYMENT_ROWS: ReadonlyArray<DeploymentRow> = [
  { label: 'Trigger', cli: "PR event in your repo's CI", server: 'Webhook from GitHub' },
  { label: 'Infrastructure', cli: 'Zero — runs in the Actions runner', server: 'A persistent server (Docker or bare metal)' },
  { label: 'State', cli: 'Stateless', server: 'SQLite (per-PR SHA + comment ID)' },
  { label: 'Scale', cli: 'One repo', server: 'Multiple repos per deployment' },
  { label: 'Auth', cli: 'GITHUB_TOKEN (auto) + ANTHROPIC_API_KEY', server: 'App JWT + installation tokens' },
  { label: 'Entry point', cli: 'scripts/run_action.py', server: 'scripts/run_server.py' }
];

/**
 * HowItWorks renders the pipeline diagram and deployment comparison panel.
 * 
 * @returns {JSX.Element} The rendered HowItWorks component.
 */
export default function HowItWorks(): JSX.Element {
  return (
    <section id="how-it-works" className="section">
      <div className="container">
        <h2>How It Works</h2>
        
        <PipelineDiagram />

        <div className={styles.tableWrapper}>
          <table className={styles.comparisonTable}>
            <thead>
              <tr>
                <th scope="col"></th>
                <th scope="col">CLI Mode (GitHub Actions)</th>
                <th scope="col">Server Mode (GitHub App)</th>
              </tr>
            </thead>
            <tbody>
              {DEPLOYMENT_ROWS.map((row, index) => (
                <tr key={index}>
                  <th scope="row">{row.label}</th>
                  <td>{row.cli}</td>
                  <td>{row.server}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className={styles.tableNote}>
          <em>Both modes run the same review engine and produce identical output.</em>
        </p>

        <div className={styles.ctaWrapper}>
          <Link href="/docs/architecture" className={styles.ctaLink}>
            See the full architecture →
          </Link>
        </div>
      </div>
    </section>
  );
}
