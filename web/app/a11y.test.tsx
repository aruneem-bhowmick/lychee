import React from 'react';
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

expect.extend(toHaveNoViolations);

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/components/CodeBlock', () => ({
  default: () => <div data-testid="code-block-mock">CodeBlock Mock</div>,
}));

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

import Home from './page';
import DocsIndexPage from './docs/page';
import { getDocBySlug } from '@/lib/docs';

const mockedGetDocBySlug = vi.mocked(getDocBySlug);

describe('Accessibility audit', () => {
  beforeEach(() => {
    mockedGetDocBySlug.mockClear();
  });

  it('the landing page has no axe violations', async () => {
    const { container } = render(<Home />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 20000);

  it('the docs index page has no axe violations', async () => {
    const { container } = render(<DocsIndexPage />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  describe('reduced motion', () => {
    const originalMatchMedia = window.matchMedia;

    beforeEach(() => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }));
    });

    afterEach(() => {
      window.matchMedia = originalMatchMedia;
    });

    it('renders landing page content fully without requiring animation to complete, when reduced motion is preferred', () => {
      expect(window.matchMedia('(prefers-reduced-motion: reduce)').matches).toBe(true);

      const { container } = render(<Home />);

      // ScrollReveal/PipelineDiagram default to a fully-visible base state
      // (opacity: 1, no transform) before any reveal class is applied —
      // motion is additive, so content never depends on JS/CSS animation
      // to be visible, satisfying prefers-reduced-motion.
      expect(container.querySelectorAll('[class*="reveal"]').length).toBeGreaterThan(0);
      container.querySelectorAll<HTMLElement>('[class*="reveal"]').forEach((el) => {
        expect(el).not.toHaveStyle({ display: 'none' });
      });
    });

    it('passes the same axe checks with reduced motion preferred', async () => {
      const { container } = render(<Home />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    }, 20000);
  });
});
