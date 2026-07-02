'use client';

import React, { useEffect, useRef, useState } from 'react';
import styles from './PipelineDiagram.module.css';

/**
 * Represents a single stage in the review process pipeline.
 */
export interface PipelineStage {
  /** The primary short noun phrase describing the stage. */
  label: string;
  /** Optional parenthetical or annotation detail for the stage. */
  detail?: string;
  /** True if this step is optional (e.g., triage step). */
  optional?: boolean;
}

/**
 * The seven stages of the Lychee code review pipeline.
 * Each object defines the label, detail, and optional annotation.
 */
export const PIPELINE_STAGES: ReadonlyArray<PipelineStage> = [
  { label: 'PR Event' },
  { label: 'Context Assembly (diff, files, commits, metadata)' },
  { label: 'Triage Pass', detail: 'Haiku classifies trivial vs. substantive', optional: true },
  { label: 'Model Selection (Haiku / Sonnet / Opus based on size + scope rules)' },
  { label: 'Prompt Construction (persona + rubric + PR context + conventions)' },
  { label: 'Claude API (structured tool call → ReviewResult)' },
  { label: 'Render + Post (Nectar → The Peel → Pits → upsert comment)' }
];

/** Per-stage stagger delay, in milliseconds, applied to the sequential fade-in once the diagram scrolls into view. */
const STAGE_REVEAL_DELAY_MS = 80;

/**
 * PipelineDiagram component displays a CSS-drawn vertical pipeline
 * showing the sequence of review stages in the Lychee architecture.
 * Stages fade in one after another, staggered by stage index, the first
 * time the diagram scrolls into view; they remain fully visible by
 * default so the diagram never depends on JavaScript to be readable.
 *
 * @returns {JSX.Element} The rendered pipeline diagram component.
 */
export default function PipelineDiagram(): JSX.Element {
  const ref = useRef<HTMLOListElement | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setInView(true);
            observer.disconnect();
          }
        });
      },
      { threshold: 0.1 }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <ol ref={ref} className={`${styles.pipeline} ${inView ? styles.inView : ''}`}>
      {PIPELINE_STAGES.map((stage, index) => (
        <li key={index} className={styles.stageItem}>
          <div
            className={`${styles.stageCard} stage`}
            data-stage-index={index}
            style={{ animationDelay: `${index * STAGE_REVEAL_DELAY_MS}ms` }}
          >
            {stage.optional && (
              <span className={styles.optionalBadge}>Optional</span>
            )}
            <div className={styles.stageLabel}>{stage.label}</div>
            {stage.detail && <div className={styles.stageDetail}>{stage.detail}</div>}
          </div>
          {index < PIPELINE_STAGES.length - 1 && (
            <span aria-hidden="true" className={styles.arrow}>↓</span>
          )}
        </li>
      ))}
    </ol>
  );
}
