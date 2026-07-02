import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { axe, toHaveNoViolations } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

expect.extend(toHaveNoViolations);

vi.mock('node:fs', () => {
  const readFileSync = vi.fn();
  return { readFileSync, default: { readFileSync } };
});

import { readFileSync } from 'node:fs';
import { DOC_SLUGS } from '../../../lib/docs';
import DocPageRoute, { generateStaticParams } from './page';

const mockedReadFileSync = vi.mocked(readFileSync);

const FIXTURE = [
  '# Glossary',
  '',
  'Intro paragraph with a [config link](CONFIGURATION.md#scope-rules) and an external [repo](https://github.com/example).',
  '',
  '## Overview',
  '',
  '| Name | Value |',
  '|------|-------|',
  '| Alpha | 1 |',
  '',
  '```bash',
  'echo hi',
  '```',
  '',
].join('\n');

/**
 * Renders the async DocPageRoute server component synchronously for tests,
 * matching the convention used for other async server components in this
 * codebase.
 *
 * @param element - The `<DocPageRoute params={...} />` element to render.
 * @returns The result of `render()` from Testing Library.
 */
async function renderRoute(element: JSX.Element) {
  const resolved = await (element.type as (props: unknown) => Promise<JSX.Element>)(
    element.props
  );
  return render(resolved);
}

describe('DocPageRoute', () => {
  beforeEach(() => {
    mockedReadFileSync.mockReset();
    mockedReadFileSync.mockReturnValue(FIXTURE);
  });

  /**
   * Unit tests for generateStaticParams(), independent of rendering.
   */
  describe('Unit: generateStaticParams', () => {
    it('returns one params object per known doc slug', () => {
      expect(generateStaticParams()).toEqual(DOC_SLUGS.map((slug) => ({ slug })));
    });
  });

  /**
   * Sanity: the route opts into static generation and resolves the
   * requested slug.
   */
  describe('Sanity', () => {
    it('exports dynamic = "force-static"', async () => {
      const mod = await import('./page');
      expect(mod.dynamic).toBe('force-static');
    });

    it('returns exactly 11 params matching DOC_SLUGS', () => {
      const params = generateStaticParams();
      expect(params).toHaveLength(11);
      expect(params.map((p) => p.slug)).toEqual([...DOC_SLUGS]);
    });
  });

  /**
   * Component: renders the sidebar, title, table, code block, and rewrites
   * an internal link, from a mocked filesystem fixture.
   */
  describe('Component: rendering', () => {
    it('renders the doc title alongside the sidebar', async () => {
      await renderRoute(<DocPageRoute params={{ slug: 'glossary' }} />);

      expect(screen.getByRole('heading', { level: 1, name: 'Glossary' })).toBeInTheDocument();
      expect(screen.getByRole('navigation', { name: 'Documentation' })).toBeInTheDocument();
    });

    it('renders the GFM table with real <table> markup', async () => {
      await renderRoute(<DocPageRoute params={{ slug: 'glossary' }} />);

      expect(screen.getByRole('table')).toBeInTheDocument();
      expect(screen.getByText('Alpha')).toBeInTheDocument();
    });

    it('renders a highlighted code block', async () => {
      const { container } = await renderRoute(<DocPageRoute params={{ slug: 'glossary' }} />);
      expect(container.querySelector('pre')).toBeInTheDocument();
      expect(container.textContent).toContain('echo hi');
    });

    it('rewrites the internal doc link and leaves the external one untouched', async () => {
      await renderRoute(<DocPageRoute params={{ slug: 'glossary' }} />);

      const internal = screen.getByRole('link', { name: 'config link' });
      expect(internal).toHaveAttribute('href', '/docs/configuration#scope-rules');

      const external = screen.getByRole('link', { name: 'repo' });
      expect(external).toHaveAttribute('href', 'https://github.com/example');
    });

    it('assigns a slug id to the second-level heading', async () => {
      await renderRoute(<DocPageRoute params={{ slug: 'glossary' }} />);
      expect(screen.getByRole('heading', { level: 2, name: 'Overview' })).toHaveAttribute(
        'id',
        'overview'
      );
    });
  });

  /**
   * Accessibility scan of a fully rendered doc page.
   */
  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = await renderRoute(<DocPageRoute params={{ slug: 'glossary' }} />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  /**
   * Smoke: importing the route module and rendering with minimal props
   * does not throw.
   */
  describe('Smoke', () => {
    it('renders without crashing', async () => {
      await expect(
        renderRoute(<DocPageRoute params={{ slug: 'glossary' }} />)
      ).resolves.toBeDefined();
    });
  });
});
