import { readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import type { Metadata } from 'next';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/font/google', () => ({
  Inter: () => ({ variable: '--font-inter' }),
  JetBrains_Mono: () => ({ variable: '--font-jetbrains-mono' }),
}));

vi.mock('@/lib/docs', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/docs')>();
  return {
    ...actual,
    getDocBySlug: vi.fn((slug: string) => ({
      slug,
      title: 'Configuration',
      description: 'Configure Lychee for your repository.',
      content: '',
    })),
  };
});

import { getDocBySlug } from '@/lib/docs';
import * as rootLayout from './layout';
import * as landingPage from './page';
import * as docsIndexPage from './docs/page';
import { generateMetadata as generateDocMetadata } from './docs/[slug]/page';

const mockedGetDocBySlug = vi.mocked(getDocBySlug);

const SITE_URL = 'https://lychee.vercel.app';
const VALUE_PROPOSITION =
  'Self-hosted, Claude-powered PR reviews that run concurrently, report cost to the cent, and never post twice.';

/** Narrows a resolved `Metadata.title` down to its `{ default, template }` shape for assertions. */
function asDefaultTemplate(title: Metadata['title']): { default: string; template: string | null } {
  return title as { default: string; template: string | null };
}

/** Narrows a resolved `Metadata.title` down to its `{ absolute }` shape for assertions. */
function asAbsolute(title: Metadata['title']): { absolute: string } {
  return title as { absolute: string };
}

const BANNED_WORDS = /powerful|seamless|easy to use|best-in-class|next-generation/i;

/**
 * Reads a PNG's declared width/height straight out of its IHDR chunk,
 * without pulling in an image-decoding dependency just for a test.
 *
 * @param filePath - Absolute path to the PNG file.
 * @returns The image's declared pixel dimensions.
 */
function readPngDimensions(filePath: string): { width: number; height: number } {
  const buffer = readFileSync(filePath);
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

describe('SEO metadata', () => {
  beforeEach(() => {
    mockedGetDocBySlug.mockClear();
  });

  /**
   * Unit tests for the root layout's base metadata: the title template,
   * default description, and Open Graph defaults every route inherits.
   */
  describe('Unit: root layout base metadata', () => {
    it('sets metadataBase to the deployed domain', () => {
      expect(rootLayout.metadata.metadataBase?.toString()).toBe(`${SITE_URL}/`);
    });

    it('sets the default title and the docs title template', () => {
      const title = asDefaultTemplate(rootLayout.metadata.title);
      expect(title.default).toBe('Lychee — Peel back your pull requests');
      expect(title.template).toBe('%s · Lychee Docs');
    });

    it('sets the base description to the canonical value proposition', () => {
      expect(rootLayout.metadata.description).toBe(VALUE_PROPOSITION);
    });

    it('sets Open Graph defaults referencing the committed OG image', () => {
      expect(rootLayout.metadata.openGraph?.title).toBe('Lychee — Peel back your pull requests');
      expect(rootLayout.metadata.openGraph?.description).toBe(VALUE_PROPOSITION);
      expect(rootLayout.metadata.openGraph?.images).toEqual(['/og-image.png']);
      expect(rootLayout.metadata.openGraph?.siteName).toBe('Lychee');
      expect((rootLayout.metadata.openGraph as { type?: string } | null)?.type).toBe('website');
    });
  });

  /**
   * Unit tests for the landing page's metadata overrides: an absolute
   * title (opting out of the docs title template) and the root canonical.
   */
  describe('Unit: landing page metadata', () => {
    it('sets an absolute title so the docs template does not apply', () => {
      const title = asAbsolute(landingPage.metadata.title);
      expect(title.absolute).toBe('Lychee — Peel back your pull requests');
    });

    it('sets the description to the canonical value proposition', () => {
      expect(landingPage.metadata.description).toBe(VALUE_PROPOSITION);
    });

    it('sets the canonical URL to the site root', () => {
      expect(landingPage.metadata.alternates?.canonical).toBe(`${SITE_URL}/`);
    });

    it('mirrors the title and description in openGraph', () => {
      expect(landingPage.metadata.openGraph?.title).toBe('Lychee — Peel back your pull requests');
      expect(landingPage.metadata.openGraph?.description).toBe(VALUE_PROPOSITION);
      expect(landingPage.metadata.openGraph?.images).toEqual(['/og-image.png']);
    });
  });

  /**
   * Unit tests for the docs index metadata: a plain string title (so the
   * template renders "Documentation · Lychee Docs") and its canonical.
   */
  describe('Unit: docs index metadata', () => {
    it('sets a plain string title of "Documentation"', () => {
      expect(docsIndexPage.metadata.title).toBe('Documentation');
    });

    it('sets a short docs-index description', () => {
      expect(docsIndexPage.metadata.description).toBe(
        'Everything you need to evaluate, run, and contribute to Lychee.'
      );
    });

    it('sets the canonical URL to /docs', () => {
      expect(docsIndexPage.metadata.alternates?.canonical).toBe(`${SITE_URL}/docs`);
    });

    it('references the committed OG image', () => {
      expect(docsIndexPage.metadata.openGraph?.images).toEqual(['/og-image.png']);
    });
  });

  /**
   * API/Data: `generateMetadata` for `/docs/[slug]` resolves its title,
   * description, and canonical from `getDocBySlug`, mocked here so the
   * assertions don't depend on real doc content.
   */
  describe('API/Data: dynamic doc metadata', () => {
    it('calls getDocBySlug with the requested slug', async () => {
      await generateDocMetadata({ params: Promise.resolve({ slug: 'configuration' }) });
      expect(mockedGetDocBySlug).toHaveBeenCalledWith('configuration');
    });

    it('sets title/description from the resolved doc', async () => {
      const metadata = await generateDocMetadata({ params: Promise.resolve({ slug: 'configuration' }) });
      expect(metadata.title).toBe('Configuration');
      expect(metadata.description).toBe('Configure Lychee for your repository.');
    });

    it('builds the Open Graph title using the docs template explicitly', async () => {
      const metadata = await generateDocMetadata({ params: Promise.resolve({ slug: 'configuration' }) });
      expect(metadata.openGraph?.title).toBe('Configuration · Lychee Docs');
      expect(metadata.openGraph?.description).toBe('Configure Lychee for your repository.');
      expect(metadata.openGraph?.images).toEqual(['/og-image.png']);
    });

    it('sets the canonical URL to the slug-specific doc route', async () => {
      const metadata = await generateDocMetadata({ params: Promise.resolve({ slug: 'configuration' }) });
      expect(metadata.alternates?.canonical).toBe(`${SITE_URL}/docs/configuration`);
    });

    it('resolves a different canonical URL for a different slug', async () => {
      const metadata = await generateDocMetadata({ params: Promise.resolve({ slug: 'glossary' }) });
      expect(metadata.alternates?.canonical).toBe(`${SITE_URL}/docs/glossary`);
    });
  });

  /**
   * Component: N/A — metadata is resolved to `<head>` tags by the Next.js
   * framework at the route-segment level, not rendered as DOM by these
   * page/layout components in a unit test. Covered by the Unit assertions
   * on the exported objects above.
   */
  describe('Component', () => {
    it.skip('N/A — metadata is not rendered DOM in RSC unit tests; covered by Unit tests above.');
  });

  /**
   * Accessibility: N/A — metadata/head tags are not DOM subject to axe.
   */
  describe('Accessibility', () => {
    it.skip('N/A — metadata/head tags are not subject to axe DOM accessibility checks.');
  });

  /**
   * Smoke: every route's metadata can be imported/computed without
   * throwing, and the committed OG image exists with the right shape.
   */
  describe('Smoke', () => {
    it('resolves metadata for every route without throwing', async () => {
      expect(rootLayout.metadata).toBeDefined();
      expect(landingPage.metadata).toBeDefined();
      expect(docsIndexPage.metadata).toBeDefined();
      await expect(generateDocMetadata({ params: Promise.resolve({ slug: 'roadmap' }) })).resolves.toBeDefined();
    });

    it('commits og-image.png as a non-zero-byte file', () => {
      const ogImagePath = path.join(__dirname, '..', 'public', 'og-image.png');
      const stats = statSync(ogImagePath);
      expect(stats.size).toBeGreaterThan(0);
    });

    it('commits og-image.png as a real 1200x630 PNG', () => {
      const ogImagePath = path.join(__dirname, '..', 'public', 'og-image.png');
      const signature = readFileSync(ogImagePath).subarray(0, 8);
      expect(signature.toString('hex')).toBe('89504e470d0a1a0a');

      const { width, height } = readPngDimensions(ogImagePath);
      expect(width).toBe(1200);
      expect(height).toBe(630);
    });
  });

  /**
   * Sanity: narrow invariants that guard against silent metadata drift —
   * the canonical domain, OG image path, and a banned-word sweep.
   */
  describe('Sanity', () => {
    it('resolves metadataBase to the deployed domain exactly', () => {
      expect(rootLayout.metadata.metadataBase).toEqual(new URL(SITE_URL));
    });

    it('references /og-image.png as the OG image on every route', async () => {
      const docMetadata = await generateDocMetadata({ params: Promise.resolve({ slug: 'configuration' }) });
      [
        rootLayout.metadata.openGraph?.images,
        landingPage.metadata.openGraph?.images,
        docsIndexPage.metadata.openGraph?.images,
        docMetadata.openGraph?.images,
      ].forEach((images) => expect(images).toEqual(['/og-image.png']));
    });

    it('never uses a banned word in any description', async () => {
      const docMetadata = await generateDocMetadata({ params: Promise.resolve({ slug: 'configuration' }) });
      [
        rootLayout.metadata.description,
        landingPage.metadata.description,
        docsIndexPage.metadata.description,
        docMetadata.description,
      ].forEach((description) => expect(description ?? '').not.toMatch(BANNED_WORDS));
    });

    it('reproduces the value-prop sentence verbatim on the base and landing metadata', () => {
      expect(rootLayout.metadata.description).toBe(landingPage.metadata.description);
      expect(rootLayout.metadata.description).toBe(VALUE_PROPOSITION);
    });
  });

  /**
   * Regression: serialized-metadata snapshots lock titles, descriptions,
   * and canonicals so future edits can't silently drift them.
   */
  describe('Regression: serialized metadata snapshots', () => {
    it('matches the landing page metadata snapshot', () => {
      expect(landingPage.metadata).toMatchSnapshot();
    });

    it('matches the docs index metadata snapshot', () => {
      expect(docsIndexPage.metadata).toMatchSnapshot();
    });

    it('matches a sample doc metadata snapshot', async () => {
      const metadata = await generateDocMetadata({ params: Promise.resolve({ slug: 'configuration' }) });
      expect(metadata).toMatchSnapshot();
    });
  });

  /**
   * End-to-end: N/A in this prompt — covered by the metadata-object unit
   * tests above; a Playwright check of `document.title` / canonical link
   * tags on built pages is optional follow-up polish work.
   */
  describe('End-to-end', () => {
    it.skip('N/A — covered by metadata-object unit tests above.');
  });

  /**
   * Responsive/Mobile: N/A — metadata is resolved independently of
   * viewport size.
   */
  describe('Responsive/Mobile', () => {
    it.skip('N/A — metadata is viewport-independent.');
  });
});
