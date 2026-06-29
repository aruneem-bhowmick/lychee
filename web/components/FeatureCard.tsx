import React from 'react';
import styles from './FeatureCard.module.css';

export interface FeatureCardProps {
  icon: string;
  title: string;
  body: string;
}

/**
 * Renders a single feature highlight card displaying an icon, title, and body description.
 *
 * @param props - The properties for the FeatureCard, including the icon emoji, title string, and body text.
 * @returns The rendered article element representing the feature card.
 */
export default function FeatureCard({ icon, title, body }: FeatureCardProps): JSX.Element {
  return (
    <article className={styles.card}>
      <span className={styles.icon} aria-hidden="true">
        {icon}
      </span>
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.body}>{body}</p>
    </article>
  );
}
