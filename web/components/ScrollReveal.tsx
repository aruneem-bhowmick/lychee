'use client';

import React, { useEffect, useRef, useState } from 'react';
import styles from './ScrollReveal.module.css';

export interface ScrollRevealProps {
  children: React.ReactNode;
  /** Wrapper tag rendered around children. Defaults to 'div'. */
  as?: keyof JSX.IntrinsicElements;
  /** Stagger delay, in milliseconds, applied to the reveal animation. Defaults to 0. */
  delayMs?: number;
}

/**
 * Wraps its children in an element that fades up into view the first time
 * it scrolls into the viewport, via IntersectionObserver.
 *
 * Progressive enhancement: children are fully visible (opacity 1, no
 * transform) before the observer ever fires, and remain visible if
 * IntersectionObserver isn't available, so content is never hidden from
 * users without JavaScript or with an unsupported browser.
 *
 * @param props - Children to reveal, an optional wrapper tag, and an optional stagger delay.
 * @returns The wrapper element, revealed on first intersection.
 */
export default function ScrollReveal({ children, as = 'div', delayMs = 0 }: ScrollRevealProps): JSX.Element {
  const ref = useRef<HTMLElement | null>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === 'undefined') {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setRevealed(true);
            observer.disconnect();
          }
        });
      },
      { threshold: 0.1, rootMargin: '0px 0px -10% 0px' }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const Tag = as as React.ElementType;

  return (
    <Tag
      ref={ref}
      className={`${styles.reveal} ${revealed ? styles.revealed : ''}`}
      style={delayMs ? { animationDelay: `${delayMs}ms` } : undefined}
    >
      {children}
    </Tag>
  );
}
