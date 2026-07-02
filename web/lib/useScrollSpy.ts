'use client';

import { useEffect, useState } from 'react';

export interface UseScrollSpyOptions {
  /** Section ids to observe, in document order. */
  sectionIds: string[];
  /** IntersectionObserver rootMargin biasing the "active" band toward the viewport center. */
  rootMargin?: string;
}

/**
 * Tracks which of the given section ids is currently most visible in the
 * viewport, for driving live scroll-spy navigation highlighting.
 *
 * Only observes ids that actually exist in the DOM, so it is a no-op (and
 * simply returns the first configured id) on routes that don't render the
 * landing page's sections. Also no-ops when `IntersectionObserver` isn't
 * available (SSR, or a test environment without the API), so it is safe
 * to call unconditionally from a component rendered on every route.
 *
 * @param opts - The section ids to observe and an optional rootMargin.
 * @returns The id of the currently most-visible observed section.
 */
export function useScrollSpy({ sectionIds, rootMargin = '-45% 0px -45% 0px' }: UseScrollSpyOptions): string {
  const [activeId, setActiveId] = useState<string>(sectionIds[0] ?? '');

  useEffect(() => {
    if (typeof window === 'undefined' || typeof IntersectionObserver === 'undefined') {
      return;
    }

    const elements = sectionIds
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);

    if (elements.length === 0) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (visible.length === 0) {
          return;
        }
        const mostVisible = visible.reduce((most, entry) =>
          entry.intersectionRatio > most.intersectionRatio ? entry : most
        );
        setActiveId(mostVisible.target.id);
      },
      { rootMargin, threshold: [0, 0.25, 0.5, 0.75, 1] }
    );

    elements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, [sectionIds, rootMargin]);

  return activeId;
}
