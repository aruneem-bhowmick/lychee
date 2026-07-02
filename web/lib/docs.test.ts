import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('node:fs', () => {
  const readFileSync = vi.fn();
  return { readFileSync, default: { readFileSync } };
});

import { readFileSync } from 'node:fs';
import { DOC_SLUGS, SLUG_TO_FILE, getAllDocSlugs, getDocBySlug } from './docs';

const mockedReadFileSync = vi.mocked(readFileSync);

describe('docs lib', () => {
  beforeEach(() => {
    mockedReadFileSync.mockReset();
  });

  /**
   * Pure, static invariants of the slug/filename mapping.
   */
  describe('Unit: SLUG_TO_FILE and DOC_SLUGS', () => {
    it('maps configuration to docs/CONFIGURATION.md', () => {
      expect(SLUG_TO_FILE.configuration).toBe('docs/CONFIGURATION.md');
    });

    it('contains exactly 11 entries', () => {
      expect(Object.keys(SLUG_TO_FILE)).toHaveLength(11);
    });

    it('exposes DOC_SLUGS in the canonical sidebar order', () => {
      expect(DOC_SLUGS).toEqual([
        'getting-started',
        'configuration',
        'commands',
        'architecture',
        'glossary',
        'deployment',
        'security',
        'canary-setup',
        'api-reference',
        'development',
        'roadmap',
      ]);
    });
  });

  /**
   * getAllDocSlugs() sanity checks.
   */
  describe('Sanity: getAllDocSlugs', () => {
    it('returns exactly 11 slugs matching DOC_SLUGS', () => {
      const slugs = getAllDocSlugs();
      expect(slugs).toHaveLength(11);
      expect(slugs).toEqual([...DOC_SLUGS]);
    });

    it('returns a new array each call (not a live reference)', () => {
      expect(getAllDocSlugs()).not.toBe(getAllDocSlugs());
    });
  });

  /**
   * getDocBySlug() reading, parsing, and fallback-derivation behavior,
   * exercised against a mocked filesystem.
   */
  describe('API/Data: getDocBySlug', () => {
    it('parses frontmatter title/description when present', () => {
      mockedReadFileSync.mockReturnValue(
        '---\ntitle: Custom Title\ndescription: Custom description.\n---\n# Heading\n\nBody text here.\n'
      );

      const doc = getDocBySlug('configuration');

      expect(doc.slug).toBe('configuration');
      expect(doc.title).toBe('Custom Title');
      expect(doc.description).toBe('Custom description.');
      expect(doc.content).toContain('# Heading');
      expect(doc.content).not.toContain('title: Custom Title');
    });

    it('derives title from the first H1 when frontmatter is absent', () => {
      mockedReadFileSync.mockReturnValue(
        '# Getting Started\n\nSet up things quickly. More detail follows.\n'
      );

      const doc = getDocBySlug('getting-started');

      expect(doc.title).toBe('Getting Started');
      expect(doc.description).toBe('Set up things quickly.');
    });

    it('falls back to a humanized slug when no frontmatter and no H1 exist', () => {
      mockedReadFileSync.mockReturnValue('Just a paragraph, no heading at all.\n');

      const doc = getDocBySlug('canary-setup');

      expect(doc.title).toBe('Canary Setup');
    });

    it('skips a leading table block when deriving the description', () => {
      mockedReadFileSync.mockReturnValue(
        '# Config\n\n| Key | Value |\n|-----|-------|\n| a | b |\n\nActual prose comes after the table.\n'
      );

      const doc = getDocBySlug('configuration');

      expect(doc.description).toBe('Actual prose comes after the table.');
    });

    it('reads from the resolved path under DOCS_DIR', () => {
      mockedReadFileSync.mockReturnValue('# X\n\nY.\n');

      getDocBySlug('configuration');

      const calledPath = String(mockedReadFileSync.mock.calls[0][0]).replace(/\\/g, '/');
      expect(calledPath).toMatch(/docs\/CONFIGURATION\.md$/);
    });

    it('throws (via notFound) for an unknown slug', () => {
      expect(() => getDocBySlug('not-a-real-slug')).toThrow();
      expect(mockedReadFileSync).not.toHaveBeenCalled();
    });
  });

  /**
   * Regression fixture locking exact title/description derivation for a
   * doc shaped like the real markdown corpus (multi-line first paragraph).
   */
  describe('Regression: multi-line first paragraph', () => {
    it('collapses a wrapped first sentence into a single description', () => {
      mockedReadFileSync.mockReturnValue(
        '# Architecture\n\nLychee is an automated PR review tool powered by Claude. It reads pull\nrequest diffs from GitHub.\n'
      );

      const doc = getDocBySlug('architecture');

      expect(doc.description).toBe(
        'Lychee is an automated PR review tool powered by Claude.'
      );
    });
  });

  /**
   * Smoke test: importing the module and calling its simplest function
   * does not throw.
   */
  describe('Smoke', () => {
    it('imports without throwing and exposes working exports', () => {
      expect(() => getAllDocSlugs()).not.toThrow();
      expect(typeof getDocBySlug).toBe('function');
    });
  });
});
