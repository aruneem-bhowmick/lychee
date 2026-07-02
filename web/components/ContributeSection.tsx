import React from 'react';
import Link from 'next/link';
import CodeBlock from './CodeBlock';
import styles from './ContributeSection.module.css';

export interface StandardRow {
  standard: string;
  enforcedBy: string;
}

export const STANDARDS: ReadonlyArray<StandardRow> = [
  { standard: 'Type annotations (strict)', enforcedBy: 'mypy --strict' },
  { standard: 'Linting', enforcedBy: 'ruff' },
  { standard: 'Formatting', enforcedBy: 'black (100-char line length)' },
  { standard: 'Immutable models', enforcedBy: 'Pydantic frozen=True' },
  { standard: 'Pure functions for prompt & render', enforcedBy: 'Asserted by unit tests' },
  { standard: 'No global state', enforcedBy: 'Code review' },
];

const renderEnforcedBy = (text: string): React.ReactNode => {
  if (text === 'mypy --strict') return <code>{text}</code>;
  if (text === 'ruff') return <code>{text}</code>;
  if (text === 'black (100-char line length)') return <><code>black</code> (100-char line length)</>;
  if (text === 'Pydantic frozen=True') return <>Pydantic <code>frozen=True</code></>;
  return text;
};

/**
 * Renders the Contribute section for the landing page.
 * Includes instructions for setting up the dev environment, running tests,
 * coding standards, contribution workflow, and security reporting.
 */
export default function ContributeSection(): JSX.Element {
  return (
    <section id="contribute" className="section">
      <div className="container">
        <h2>Contribute</h2>
        
        <div className={styles.content}>
          <div className={styles.setup}>
            <h3>1. Clone and install</h3>
            <CodeBlock lang="bash" code={`git clone https://github.com/aspect-analytics/lychee.git
cd lychee
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
pre-commit install`} />
          </div>

          <div className={styles.setup}>
            <h3>2. Run the test suite</h3>
            <CodeBlock lang="bash" code="pytest" />
            <blockquote className={styles.callout}>
              Coverage is enforced at 80% (branch coverage). The default invocation excludes <code>e2e</code> tests, which require live GitHub and Claude API access. See <Link href="/docs/canary-setup">Canary Setup</Link> to configure those.
            </blockquote>
            <CodeBlock lang="bash" code={`# Update golden snapshots after intentional render changes
pytest --snapshot-update`} />
          </div>

          <div className={styles.setup}>
            <h3>3. Code standards at a glance</h3>
            <div className={styles.tableWrapper}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th scope="col">Standard</th>
                    <th scope="col">Enforced by</th>
                  </tr>
                </thead>
                <tbody>
                  {STANDARDS.map((row, idx) => (
                    <tr key={idx}>
                      <td>{row.standard}</td>
                      <td>{renderEnforcedBy(row.enforcedBy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>CI runs lint → type-check → engine integrity hash → test on every PR. All gates must be green before merge.</p>
          </div>
        </div>

        <div className={styles.workflow}>
          <h3>Contribution Workflow</h3>
          <ol>
            <li>Fork the repository and create a feature branch.</li>
            <li>Make your changes; ensure <code>pytest</code> and <code>mypy</code> pass locally.</li>
            <li>Use <code>lychee review --dry-run --fixture tests/fixtures/pr_payload.json</code> to preview rendering changes without API calls.</li>
            <li>Open a PR — Lychee will review it automatically.</li>
          </ol>
        </div>

        <aside className={styles.securityNotice} aria-label="Security reporting">
          <p>
            <strong>Found a security issue?</strong> Do not open a public GitHub issue. Email the maintainers directly or use GitHub&apos;s private vulnerability reporting (<strong>Security tab → Report a vulnerability</strong>). We acknowledge within 48 hours and provide a fix timeline within 7 days.
          </p>
        </aside>

        <div className={styles.ctas}>
          <Link href="/docs/development" className={styles.ctaLink}>Development guide →</Link>
          <Link href="/docs/roadmap" className={styles.ctaLink}>Roadmap →</Link>
        </div>
      </div>
    </section>
  );
}
