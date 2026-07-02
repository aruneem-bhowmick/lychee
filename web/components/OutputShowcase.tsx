import React from 'react';
import styles from './OutputShowcase.module.css';
import Link from 'next/link';

export interface PitRow {
  severityEmoji: string;
  severity: string;
  category: string;
  finding: React.ReactNode;
}

export interface Annotation {
  target: 'ripeness' | 'nectar' | 'peel' | 'pits' | 'footer';
  label: string;
}

export const PITS_DATA: PitRow[] = [
  {
    severityEmoji: '🔴',
    severity: 'critical',
    category: 'security',
    finding: (
      <>
        <code className={styles.inlineCode}>stripe.py:47</code> — Webhook payload is processed without verifying the <code className={styles.inlineCode}>Stripe-Signature</code> header. An attacker can POST arbitrary payloads and trigger order status changes. Use <code className={styles.inlineCode}>stripe.Webhook.construct_event()</code> with your webhook secret.
      </>
    )
  },
  {
    severityEmoji: '🟠',
    severity: 'major',
    category: 'correctness',
    finding: (
      <>
        <code className={styles.inlineCode}>order.py:83</code> — <code className={styles.inlineCode}>update_status()</code> accepts any target status without validating the transition. A <code className={styles.inlineCode}>completed</code> order can be moved back to <code className={styles.inlineCode}>pending</code>, which may cause double-fulfillment.
      </>
    )
  },
  {
    severityEmoji: '🟡',
    severity: 'minor',
    category: 'tests',
    finding: (
      <>
        <code className={styles.inlineCode}>test_stripe_webhook.py</code> — No test for an invalid or missing <code className={styles.inlineCode}>Stripe-Signature</code> header. Add a test confirming a <code className={styles.inlineCode}>400</code> response and no database write on bad signatures.
      </>
    )
  }
];

/**
 * OutputShowcase renders a mock GitHub PR review comment from Lychee with annotations.
 */
export default function OutputShowcase(): JSX.Element {
  return (
    <section id="output" className={`section ${styles.section}`}>
      <div className="container">
        <h2 className={styles.title}>What you&apos;ll see in your PR</h2>
        
        <div className={styles.showcaseWrapper}>
          <div className={styles.prContext}>
            Repository: <code className={styles.inlineCode}>acme-corp/billing-service</code><br />
            PR title: <code className={styles.inlineCode}>feat: add Stripe webhook handler for payment events</code><br />
            Author: <code className={styles.inlineCode}>@dev</code>
          </div>
          
          <div className={styles.commentFrame}>
            <div className={styles.headerStrip}>
              <div className={styles.avatar}></div>
              <span className={styles.author}>lychee-bot</span>
            </div>
            
            <div className={styles.commentBody}>
              <div>
                <div className={styles.monospaceText}>{'<!-- lychee:review -->'}</div>
                <div className={styles.headerTitle}>🌴 Lychee peeled this PR · claude-sonnet-4-6</div>
              </div>
              
              <div className={styles.annotatable} data-annotate="ripeness">
                <div className={styles.badge}>🟡 Unripe</div>
                <span className={styles.annotation}>Ripeness verdict: Ripe / Unripe / Sour</span>
              </div>
              
              <div className={`${styles.nectarBlock} ${styles.annotatable}`} data-annotate="nectar">
                <p>
                  This PR adds a Stripe webhook handler to process <code className={styles.inlineCode}>payment_intent.succeeded</code> and <code className={styles.inlineCode}>charge.failed</code> events, updating order status in the database. The implementation is functional but has a critical security gap in webhook signature verification and two correctness issues in the error-handling path that should be addressed before merging.
                </p>
                <span className={styles.annotation}>Nectar — the distilled summary</span>
              </div>
              
              <div className={styles.annotatable} data-annotate="peel">
                <ul className={styles.peelList}>
                  <li><code className={styles.inlineCode}>src/webhooks/stripe.py</code> — New handler module. Core logic is sound but the signature verification step is absent.</li>
                  <li><code className={styles.inlineCode}>src/models/order.py</code> — Adds <code className={styles.inlineCode}>update_status()</code>. The method does not validate the transition (e.g., <code className={styles.inlineCode}>completed → pending</code> should be rejected).</li>
                  <li><code className={styles.inlineCode}>tests/test_stripe_webhook.py</code> — Covers the happy path but lacks tests for invalid signatures and malformed payloads.</li>
                </ul>
                <span className={styles.annotation}>The Peel — file-by-file walkthrough</span>
              </div>
              
              <div className={styles.annotatable} data-annotate="pits">
                <div className={styles.pitsTableWrapper}>
                  <table className={styles.pitsTable}>
                    <thead>
                      <tr>
                        <th>Severity</th>
                        <th>Category</th>
                        <th>Finding</th>
                      </tr>
                    </thead>
                    <tbody>
                      {PITS_DATA.map((pit, idx) => (
                        <tr key={idx}>
                          <td className={`${styles.severityCell} ${styles[`severity${pit.severity}`]}`}>
                            {pit.severityEmoji} {pit.severity}
                          </td>
                          <td>{pit.category}</td>
                          <td>{pit.finding}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <span className={styles.annotation}>Pits — findings with severity &amp; category</span>
              </div>
              
              <div className={styles.annotatable} data-annotate="footer">
                <div className={styles.monospaceText}>
                  Tokens: 4,821 in · 612 out · $0.023  ·  Reviewed to the core by Lychee 🌴
                  <br />
                  {'<!-- lychee:state {"last_reviewed_sha": "a3f9c12"} -->'}
                </div>
                <span className={styles.annotation}>Cost footer — exact token usage and USD cost</span>
              </div>
            </div>
          </div>
          
          <p className={styles.closingParagraph}>
            Every Lychee review follows this structure — always one comment, always updated in place, always the same shape regardless of PR size. Severity levels: <code className={styles.inlineCode}>info</code>, <code className={styles.inlineCode}>minor</code>, <code className={styles.inlineCode}>major</code>, <code className={styles.inlineCode}>critical</code>. Categories: <code className={styles.inlineCode}>correctness</code>, <code className={styles.inlineCode}>security</code>, <code className={styles.inlineCode}>performance</code>, <code className={styles.inlineCode}>tests</code>, <code className={styles.inlineCode}>style</code>, <code className={styles.inlineCode}>docs</code>, <code className={styles.inlineCode}>other</code>. See the <Link href="/docs/glossary">Glossary</Link> for the full vocabulary.
          </p>
        </div>
      </div>
    </section>
  );
}
