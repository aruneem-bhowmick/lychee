import Link from 'next/link';
import CodeBlock from './CodeBlock';
import styles from './CommandsTable.module.css';

/**
 * Interface representing a single row in the commands table.
 */
export interface CommandRow {
  command: string;
  posts: string;
}

/**
 * The four interactive Lychee commands and their verbatim descriptions.
 */
export const COMMANDS: ReadonlyArray<CommandRow> = [
  { command: '@lychee peel', posts: 'Full review: Nectar + The Peel + Pits (same as automatic review)' },
  { command: '@lychee juice', posts: 'Nectar section only — the short summary paragraph' },
  { command: '@lychee pit', posts: 'The single highest-severity finding only' },
  { command: '@lychee ripe?', posts: 'Ripeness verdict only — 🟢 Ripe, 🟡 Unripe, or 🔴 Sour' },
];

/**
 * The supporting YAML snippet enabling commands.
 */
const YAML_SNIPPET = `features:
  commands: true

authorization:
  allowed_users:   # leave empty to allow all users
    - alice
    - bob`;

/**
 * CommandsTable component renders the interactive commands showcase,
 * a supportive configuration paragraph, a YAML configuration snippet,
 * and a call-to-action link to full command references.
 *
 * @returns The rendered server component section.
 */
export default function CommandsTable(): JSX.Element {
  return (
    <section id="commands" className={styles.section}>
      <div className={styles.container}>
        <h2 className={styles.heading}>Interactive Commands</h2>

        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Comment</th>
                <th scope="col">What it posts</th>
              </tr>
            </thead>
            <tbody>
              {COMMANDS.map((row, idx) => (
                <tr key={idx}>
                  <td>
                    <code className={styles.code}>{row.command}</code>
                  </td>
                  <td>{row.posts}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className={styles.description}>
          Commands respect all the same configuration as automatic reviews: <code>severity_threshold</code>, <code>tone</code>, <code>scope_rules</code>, <code>inline_comments</code>, and <code>cost_footer</code> all apply. Access can be restricted to specific GitHub logins via <code>authorization.allowed_users</code> in <code>.lychee.yml</code>. Unknown commands receive a help message listing all four.
        </p>

        <p className={styles.snippetTitle}>
          Enable commands by adding to .lychee.yml:
        </p>
        
        <div className={styles.codeBlockWrapper}>
          <CodeBlock 
            code={YAML_SNIPPET} 
            filename=".lychee.yml" 
            lang="yaml" 
          />
        </div>

        <Link href="/docs/commands" className={styles.cta}>
          Full command reference →
        </Link>
      </div>
    </section>
  );
}
