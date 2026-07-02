import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { axe, toHaveNoViolations } from 'jest-axe';
import { describe, expect, it } from 'vitest';
import DocsSidebar from './DocsSidebar';
import { DOC_SLUGS } from '../lib/docs';

expect.extend(toHaveNoViolations);

describe('DocsSidebar Component', () => {
  /**
   * Smoke test: renders without crashing on minimal required props.
   */
  describe('Smoke', () => {
    it('renders without crashing given only activeSlug', () => {
      render(<DocsSidebar activeSlug="configuration" />);
      expect(screen.getByRole('navigation', { name: 'Documentation' })).toBeInTheDocument();
    });
  });

  /**
   * Component rendering and structure assertions.
   */
  describe('Component: rendering', () => {
    it('renders all 11 items with hrefs pointing at /docs/<slug>', () => {
      render(<DocsSidebar activeSlug="configuration" />);
      const links = screen.getAllByRole('link');
      expect(links).toHaveLength(11);
      DOC_SLUGS.forEach((slug) => {
        const matching = links.find((link) => link.getAttribute('href') === `/docs/${slug}`);
        expect(matching).toBeTruthy();
      });
    });

    it('marks the item matching activeSlug with aria-current="page"', () => {
      render(<DocsSidebar activeSlug="configuration" />);
      const active = screen.getByRole('link', { name: 'Configuration' });
      expect(active).toHaveAttribute('aria-current', 'page');
    });

    it('does not mark non-active items with aria-current', () => {
      render(<DocsSidebar activeSlug="configuration" />);
      const other = screen.getByRole('link', { name: 'Roadmap' });
      expect(other).not.toHaveAttribute('aria-current');
    });

    it('separates the 4 canonical groups with dividers', () => {
      const { container } = render(<DocsSidebar activeSlug="glossary" />);
      const dividers = container.querySelectorAll('hr');
      expect(dividers).toHaveLength(3);
    });

    it('renders custom groups when provided', () => {
      render(
        <DocsSidebar
          activeSlug="a"
          groups={[{ items: [{ slug: 'a', label: 'Alpha' }] }]}
        />
      );
      const links = screen.getAllByRole('link');
      expect(links).toHaveLength(1);
      expect(links[0]).toHaveAttribute('href', '/docs/a');
    });
  });

  /**
   * Mobile drawer toggle behavior.
   */
  describe('Responsive/Mobile: drawer toggle', () => {
    it('starts collapsed with aria-expanded="false"', () => {
      render(<DocsSidebar activeSlug="configuration" />);
      const toggle = screen.getByRole('button', { name: 'Browse docs' });
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
    });

    it('flips aria-expanded and label when the toggle is clicked', () => {
      render(<DocsSidebar activeSlug="configuration" />);
      const toggle = screen.getByRole('button', { name: 'Browse docs' });

      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('button', { name: 'Close menu' })).toBeInTheDocument();

      fireEvent.click(toggle);
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
    });

    it('points aria-controls at the nav it toggles', () => {
      render(<DocsSidebar activeSlug="configuration" />);
      const toggle = screen.getByRole('button', { name: 'Browse docs' });
      const nav = screen.getByRole('navigation', { name: 'Documentation' });
      expect(toggle).toHaveAttribute('aria-controls', nav.id);
    });
  });

  /**
   * Accessibility: labeled nav, no axe violations.
   */
  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<DocsSidebar activeSlug="getting-started" />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('uses a nav labeled "Documentation"', () => {
      render(<DocsSidebar activeSlug="getting-started" />);
      expect(screen.getByRole('navigation', { name: 'Documentation' })).toBeInTheDocument();
    });
  });

  /**
   * Visual/Snapshot: golden render output for the default grouping.
   */
  describe('Visual/Snapshot', () => {
    it('matches the snapshot with getting-started active', () => {
      const { container } = render(<DocsSidebar activeSlug="getting-started" />);
      expect(container).toMatchSnapshot();
    });
  });

  /**
   * Sanity: exact default grouping and labels.
   */
  describe('Sanity: default grouping', () => {
    it('renders the exact canonical group labels in order', () => {
      render(<DocsSidebar activeSlug="getting-started" />);
      const labels = screen.getAllByRole('link').map((link) => link.textContent);
      expect(labels).toEqual([
        'Getting Started',
        'Configuration',
        'Commands',
        'Architecture',
        'Glossary',
        'Deployment',
        'Security',
        'Canary Setup',
        'API Reference',
        'Development',
        'Roadmap',
      ]);
    });
  });
});
