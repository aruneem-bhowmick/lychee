import React from 'react';
import FeatureCard, { FeatureCardProps } from './FeatureCard';
import styles from './FeatureHighlights.module.css';

export const FEATURES: ReadonlyArray<FeatureCardProps> = [
  {
    icon: '⚖️',
    title: 'Smart Model Tiering',
    body: 'Trivial PRs go to Haiku. Standard reviews use Sonnet. Diffs over 100,000 characters escalate automatically to Opus. Scope rules let you pin specific paths or PR labels to a different model — terraform changes can always get Opus, docs PRs can always get Haiku.',
  },
  {
    icon: '🔕',
    title: 'No-Spam Ergonomics',
    body: 'Every PR gets one review comment, identified by a hidden HTML marker. When new commits arrive, Lychee finds and updates that comment in place — no new notifications, no duplicate threads. Inline findings are fingerprinted (SHA-256) so they are never posted twice across pushes.',
  },
  {
    icon: '💰',
    title: 'Predictable Cost',
    body: 'Every review reports its exact token usage and USD cost in the comment footer. Set a `budget_cap_usd` in `.lychee.yml` and Lychee will halt and report a partial result rather than exceeding it. No surprise bills.',
  },
  {
    icon: '🗂️',
    title: 'Map-Reduce for Large PRs',
    body: "PRs exceeding 50 changed files don't get skipped or truncated. Lychee partitions them into groups of 10, reviews each group separately, then merges the results into one coherent review. The output contract is identical regardless of PR size.",
  },
  {
    icon: '💬',
    title: 'Interactive Commands',
    body: 'Drop `@lychee peel` in any PR comment for a full on-demand review. `@lychee juice` for just the summary. `@lychee pit` for the single most critical finding. `@lychee ripe?` for the merge-readiness verdict. Commands respect the same config as automatic reviews and support an allow-list for access control.',
  },
];

/**
 * Renders the Feature Highlights section of the landing page.
 * Displays a responsive grid of feature cards.
 *
 * @returns The rendered section containing the "Why Lychee" grid.
 */
export default function FeatureHighlights(): JSX.Element {
  return (
    <section id="features" className={styles.section}>
      <div className={styles.container}>
        <h2 className={styles.heading}>Why Lychee</h2>
        <div className={styles.grid}>
          {FEATURES.map((feature, idx) => (
            <FeatureCard
              key={idx}
              icon={feature.icon}
              title={feature.title}
              body={feature.body}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
