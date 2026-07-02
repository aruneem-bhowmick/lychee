import type { Metadata } from 'next';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/font/google', () => ({
  Inter: () => ({ variable: '--font-inter' }),
  JetBrains_Mono: () => ({ variable: '--font-jetbrains-mono' }),
}));

import * as rootLayout from './layout';
import * as landingPage from './page';
import * as docsIndexPage from './docs/page';

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

describe('SEO metadata', () => {
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
});
