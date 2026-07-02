import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { axe, toHaveNoViolations } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

expect.extend(toHaveNoViolations);

vi.mock('@/lib/docs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/docs')>();
  return {
    ...actual,
    getDocBySlug: vi.fn((slug: string) => ({
      slug,
      title: slug,
      description: `Description for ${slug}.`,
      content: '',
    })),
  };
});

import { DOC_SLUGS, getDocBySlug } from '@/lib/docs';
import DocsIndexPage, { DOCS_INDEX_GROUPS, dynamic } from './page';

const mockedGetDocBySlug = vi.mocked(getDocBySlug);

/**
 * Returns the 11 index entry links, scoped to the `<dl>` card lists so
 * they aren't confused with the sidebar's identically-labeled nav links.
 *
 * @param container - The rendered page's root element.
 * @returns The entry `<a>` elements, in document order.
 */
function getEntryLinks(container: HTMLElement): HTMLAnchorElement[] {
  return Array.from(container.querySelectorAll('dl a'));
}

describe('DocsIndexPage', () => {
  beforeEach(() => {
    mockedGetDocBySlug.mockClear();
  });

  /**
   * Pure, static invariants of the DOCS_INDEX_GROUPS structure.
   */
  describe('Unit: DOCS_INDEX_GROUPS', () => {
    it('has exactly 4 groups with the canonical section names in order', () => {
      expect(DOCS_INDEX_GROUPS.map((g) => g.section)).toEqual([
        'Getting Started & Configuration',
        'Architecture & Design',
        'Operations, Deployment & Security',
        'Development & Project Trajectory',
      ]);
    });

    it('assigns the exact member slugs to each group, in order', () => {
      expect(DOCS_INDEX_GROUPS.map((g) => g.slugs)).toEqual([
        ['getting-started', 'configuration', 'commands'],
        ['architecture', 'glossary'],
        ['deployment', 'security', 'canary-setup', 'api-reference'],
        ['development', 'roadmap'],
      ]);
    });

    it('covers all 11 known doc slugs exactly once, matching DOC_SLUGS', () => {
      const flattened = DOCS_INDEX_GROUPS.flatMap((g) => g.slugs);
      expect(flattened).toHaveLength(11);
      expect(new Set(flattened).size).toBe(11);
      expect(flattened).toEqual([...DOC_SLUGS]);
    });
  });

  /**
   * Rendering: headings, entry links, and per-entry descriptions pulled
   * from the (mocked) doc loader.
   */
  describe('Component: rendering', () => {
    it('renders exactly one h1 titled "Documentation"', () => {
      render(<DocsIndexPage />);
      expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Documentation');
    });

    it('renders the four group h2 headings in order', () => {
      render(<DocsIndexPage />);
      const groupHeadings = screen.getAllByRole('heading', { level: 2 });
      expect(groupHeadings.map((h) => h.textContent)).toEqual([
        'Getting Started & Configuration',
        'Architecture & Design',
        'Operations, Deployment & Security',
        'Development & Project Trajectory',
      ]);
    });

    it('renders 11 entry links with hrefs from /docs/getting-started to /docs/roadmap', () => {
      const { container } = render(<DocsIndexPage />);
      const hrefs = getEntryLinks(container).map((link) => link.getAttribute('href'));
      expect(hrefs).toEqual(DOC_SLUGS.map((slug) => `/docs/${slug}`));
    });

    it('renders a description for every entry', () => {
      render(<DocsIndexPage />);
      DOC_SLUGS.forEach((slug) => {
        expect(screen.getByText(`Description for ${slug}.`)).toBeInTheDocument();
      });
    });
  });

  /**
   * API/Data: the index pulls each doc's `description` from `getDocBySlug`
   * and renders it alongside the corresponding link.
   */
  describe('API/Data: getDocBySlug integration', () => {
    it('calls getDocBySlug exactly once per known doc slug', () => {
      render(<DocsIndexPage />);
      expect(mockedGetDocBySlug).toHaveBeenCalledTimes(11);
      DOC_SLUGS.forEach((slug) => expect(mockedGetDocBySlug).toHaveBeenCalledWith(slug));
    });
  });

  /**
   * Accessibility: axe scan plus heading-hierarchy and link-text checks.
   */
  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<DocsIndexPage />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('gives every entry link discernible accessible text', () => {
      const { container } = render(<DocsIndexPage />);
      getEntryLinks(container).forEach((link) => {
        expect(link.textContent?.trim().length).toBeGreaterThan(0);
      });
    });
  });

  /**
   * Smoke: importing and rendering the page does not throw, and it opts
   * into static generation.
   */
  describe('Smoke', () => {
    it('exports dynamic = "force-static"', () => {
      expect(dynamic).toBe('force-static');
    });

    it('renders without crashing', () => {
      expect(() => render(<DocsIndexPage />)).not.toThrow();
    });
  });

  /**
   * Sanity: exact slug-to-href mapping for the trickier labels, plus a
   * banned-word check on the authored intro copy.
   */
  describe('Sanity', () => {
    it('maps "Canary Setup" to /docs/canary-setup', () => {
      const { container } = render(<DocsIndexPage />);
      const link = getEntryLinks(container).find((a) => a.textContent === 'Canary Setup');
      expect(link).toHaveAttribute('href', '/docs/canary-setup');
    });

    it('maps "API Reference" to /docs/api-reference', () => {
      const { container } = render(<DocsIndexPage />);
      const link = getEntryLinks(container).find((a) => a.textContent === 'API Reference');
      expect(link).toHaveAttribute('href', '/docs/api-reference');
    });

    it('does not use any banned marketing words or planning-doc language in the intro', () => {
      render(<DocsIndexPage />);
      const intro = screen.getByText(
        'Everything you need to evaluate, run, and contribute to Lychee.'
      );
      const banned = /powerful|seamless|easy to use|best-in-class|next-generation|\bphase\b|LP-R/i;
      expect(intro.textContent ?? '').not.toMatch(banned);
    });
  });

  /**
   * End-to-end: full docs navigation from the index is exercised by a
   * dedicated end-to-end suite; here only component-level behavior applies.
   */
  describe('End-to-end', () => {
    it.skip('N/A — covered by component tests; full docs navigation is exercised by a separate end-to-end suite.');
  });
});
