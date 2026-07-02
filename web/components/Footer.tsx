import React from 'react';
import Link from 'next/link';
import styles from './Footer.module.css';

/**
 * Props for the Footer component.
 */
export interface FooterProps {
  /** The version of the application. Defaults to "v0.1.5". */
  version?: string;
}

/**
 * Server component representing the footer of the application.
 * Contains branding, structured link columns, and a bottom bar with version and license information.
 *
 * @param props Configuration properties for the footer.
 */
export default function Footer({ version = 'v0.1.5' }: FooterProps): JSX.Element {
  return (
    <footer className={styles.footer} role="contentinfo">
      <div className={styles.inner}>
        <div className={styles.topSection}>
          <div className={styles.brandBlock}>
            <span className={styles.brand}>Lychee</span>
            <p className={styles.tagline}>Peel back your pull requests.</p>
          </div>

          <div className={styles.linksBlock}>
            <div className={styles.linkColumn}>
              <h2 className={styles.linkHeading}>Docs</h2>
              <ul className={styles.linkList}>
                <li><Link href="/docs/getting-started" className={styles.footerLink}>Getting Started</Link></li>
                <li><Link href="/docs/configuration" className={styles.footerLink}>Configuration</Link></li>
                <li><Link href="/docs/commands" className={styles.footerLink}>Commands</Link></li>
                <li><Link href="/docs/architecture" className={styles.footerLink}>Architecture</Link></li>
                <li><Link href="/docs/deployment" className={styles.footerLink}>Deployment</Link></li>
              </ul>
            </div>

            <div className={styles.linkColumn}>
              <h3 className={styles.linkHeading}>Project</h3>
              <ul className={styles.linkList}>
                <li><a href="https://github.com/aspect-analytics/lychee" target="_blank" rel="noopener noreferrer" className={styles.footerLink}>GitHub</a></li>
                <li><a href="https://github.com/aspect-analytics/lychee/blob/main/CHANGELOG.md" target="_blank" rel="noopener noreferrer" className={styles.footerLink}>CHANGELOG</a></li>
                <li><Link href="/docs/roadmap" className={styles.footerLink}>Roadmap</Link></li>
                <li><Link href="/docs/security" className={styles.footerLink}>Security</Link></li>
                <li><Link href="/docs/glossary" className={styles.footerLink}>Glossary</Link></li>
              </ul>
            </div>
          </div>

          <div className={styles.rightBlock}>
            <p className={styles.reviewedText}>Reviewed to the core by Lychee 🌴</p>
          </div>
        </div>

        <div className={styles.bottomBar}>
          <div className={styles.bottomLinks}>
            <span className={styles.versionBadge}>{version}</span>
            <span className={styles.footerLink}>MIT License</span>
            <Link href="/docs" className={styles.footerLink}>Spec</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
