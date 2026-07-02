import React from 'react';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom';
import { toHaveNoViolations } from 'jest-axe';
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
});
