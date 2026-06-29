import React from 'react';
import styles from './Hero.module.css';

/**
 * Represents a ripeness badge indicating the review state of a pull request.
 */
export interface RipenessBadge {
  /** The emoji to display on the badge */
  emoji: string;
  /** The text label of the badge */
  label: string;
  /** The variant style of the badge, corresponding to its status */
  variant: 'ripe' | 'unripe' | 'sour';
}

/**
 * Props for the Hero component.
 */
export interface HeroProps {
  /** Optional array of custom ripeness badges to display. If not provided, defaults to the canonical three badges. */
  badges?: RipenessBadge[];
}

const defaultBadges: RipenessBadge[] = [
  { emoji: '🟢', label: 'Ripe', variant: 'ripe' },
  { emoji: '🟡', label: 'Unripe', variant: 'unripe' },
  { emoji: '🔴', label: 'Sour', variant: 'sour' },
];

/**
 * Hero section component for the landing page.
 * Displays the product tagline, value proposition, a visual badge row, and primary CTAs.
 * Designed to be a full-viewport-height section communicating core value instantly.
 *
 * @param props The component props.
 * @returns The rendered hero section.
 */
export default function Hero({ badges = defaultBadges }: HeroProps): JSX.Element {
  return (
    <section id="hero" className={styles.hero} aria-labelledby="hero-tagline">
      {/* Banner logo at top */}
      <img
        src="/lychee-banner.svg"
        alt="Lychee"
        className={styles.logo}
      />

      {/* Tagline */}
      <h1 id="hero-tagline" className={styles.tagline}>
        Peel back your pull requests.
      </h1>

      {/* Value proposition */}
      <p className={styles.valueProp}>
        Self-hosted, Claude-powered PR reviews that run concurrently, report cost to the cent, and never post twice.
      </p>

      {/* Ripeness badge row */}
      <div className={styles.badges}>
        {badges.map((b, i) => (
          <span key={i} className={styles.badge} data-variant={b.variant}>
            {b.emoji} {b.label}
          </span>
        ))}
      </div>

      {/* Primary CTAs */}
      <div className={styles.actions}>
        <a href="/#setup" className={styles.ctaPrimary}>
          Get Started
        </a>
        <a
          href="https://github.com/aspect-analytics/lychee"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.ctaSecondary}
        >
          View on GitHub
        </a>
      </div>
    </section>
  );
}
