import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { axe, toHaveNoViolations } from 'jest-axe';
import { vi, describe, it, expect } from 'vitest';

import ConfigSampler, {
  KNOBS,
  MINIMAL_YAML,
  FULL_YAML,
  MONOREPO_YAML,
} from './ConfigSampler';

expect.extend(toHaveNoViolations);

// Mock CodeBlock as it's an async server component.
vi.mock('./CodeBlock', () => {
  return {
    default: function MockCodeBlock({ code, filename, lang }: any) {
      return (
        <div data-testid="code-block" data-filename={filename} data-lang={lang}>
          {code}
        </div>
      );
    },
  };
});

/**
 * Test suite for the ConfigSampler component and its associated constant values.
 */
describe('ConfigSampler Component', () => {
  /**
   * Unit tests for the configuration constants and knob specifications.
   */
  describe('Unit: KNOBS Constant', () => {
    it('asserts KNOBS length is exactly 8', () => {
      expect(KNOBS.length).toBe(8);
    });

    it('asserts keys are in the correct order', () => {
      const keys = KNOBS.map((k) => k.key);
      expect(keys).toEqual([
        'model.default',
        'review.severity_threshold',
        'review.tone',
        'review.budget_cap_usd',
        'features.inline_comments',
        'features.triage_pass',
        'features.commands',
        'conventions_file',
      ]);
    });

    it('asserts defaults null appear for budget cap and conventions file', () => {
      const budgetCap = KNOBS.find((k) => k.key === 'review.budget_cap_usd');
      const conventions = KNOBS.find((k) => k.key === 'conventions_file');

      expect(budgetCap?.defaultValue).toBe('null');
      expect(conventions?.defaultValue).toBe('null');
    });
  });

  /**
   * Smoke test to verify importing and basic rendering of ConfigSampler.
   */
  describe('Smoke: Default Render', () => {
    it('renders without crashing with default props', () => {
      render(<ConfigSampler />);
      expect(screen.getByRole('tablist')).toBeInTheDocument();
      // Verifies that default tab is minimal
      const minimalTab = screen.getByRole('tab', { name: /Minimal/i });
      expect(minimalTab).toHaveAttribute('aria-selected', 'true');
    });
  });

  /**
   * Component behavior tests for tab interactions and panels visibility.
   */
  describe('Component Behavior', () => {
    it('asserts three tabs and default selection', () => {
      render(<ConfigSampler />);
      const minimalTab = screen.getByRole('tab', { name: /^Minimal$/i });
      const fullTab = screen.getByRole('tab', { name: /Full-featured/i });
      const monorepoTab = screen.getByRole('tab', { name: /Monorepo with scope rules/i });

      expect(minimalTab).toBeInTheDocument();
      expect(fullTab).toBeInTheDocument();
      expect(monorepoTab).toBeInTheDocument();

      expect(minimalTab).toHaveAttribute('aria-selected', 'true');
      expect(fullTab).toHaveAttribute('aria-selected', 'false');
      expect(monorepoTab).toHaveAttribute('aria-selected', 'false');
    });

    it('toggles panels visibility correctly when clicking tabs', () => {
      render(<ConfigSampler />);

      const minimalPanel = document.getElementById('panel-minimal');
      const fullPanel = document.getElementById('panel-full');
      const monorepoPanel = document.getElementById('panel-monorepo');

      // Default state (Minimal active)
      expect(minimalPanel).not.toHaveAttribute('hidden');
      expect(fullPanel).toHaveAttribute('hidden');
      expect(monorepoPanel).toHaveAttribute('hidden');
      expect(minimalPanel).toHaveTextContent('# .lychee.yml — minimal');

      // Click Full-featured
      const fullTab = screen.getByRole('tab', { name: /Full-featured/i });
      fireEvent.click(fullTab);

      expect(fullTab).toHaveAttribute('aria-selected', 'true');
      expect(minimalPanel).toHaveAttribute('hidden');
      expect(fullPanel).not.toHaveAttribute('hidden');
      expect(monorepoPanel).toHaveAttribute('hidden');
      expect(fullPanel).toHaveTextContent('budget_cap_usd: 0.50');
      expect(fullPanel).toHaveTextContent('triage: claude-haiku-4-5-20251001');

      // Click Monorepo
      const monorepoTab = screen.getByRole('tab', { name: /Monorepo with scope rules/i });
      fireEvent.click(monorepoTab);

      expect(monorepoTab).toHaveAttribute('aria-selected', 'true');
      expect(minimalPanel).toHaveAttribute('hidden');
      expect(fullPanel).toHaveAttribute('hidden');
      expect(monorepoPanel).not.toHaveAttribute('hidden');
      expect(monorepoPanel).toHaveTextContent('scope_rules:');
      expect(monorepoPanel).toHaveTextContent('labels: ["infrastructure"]');
    });

    it('asserts the knobs table renders 8 rows', () => {
      render(<ConfigSampler />);
      const rows = screen.getAllByRole('row');
      // 1 header row + 8 data rows = 9 total rows
      expect(rows.length).toBe(9);
    });

    it('asserts the CTA links to the configuration docs', () => {
      render(<ConfigSampler />);
      const ctaLink = screen.getByRole('link', { name: /Full configuration reference/i });
      expect(ctaLink).toHaveAttribute('href', '/docs/configuration');
    });
  });

  /**
   * Sanity checks verifying exact content criteria.
   */
  describe('Sanity: Exact String Matches', () => {
    it('verifies Full-featured YAML lists ignore_globs verbatim', () => {
      expect(FULL_YAML).toContain('- "**/*.lock"');
      expect(FULL_YAML).toContain('- "**/*.min.js"');
      expect(FULL_YAML).toContain('- "vendor/**"');
    });

    it('verifies review.tone knob description matches balanced / concise / detailed', () => {
      const toneKnob = KNOBS.find((k) => k.key === 'review.tone');
      expect(toneKnob?.controls).toBe('balanced / concise / detailed');
    });

    it('verifies Monorepo YAML contains exact skip generated files comment', () => {
      expect(MONOREPO_YAML).toContain('# Skip generated files entirely');
    });
  });

  /**
   * Accessibility testing (ARIA roles, keyboard shortcuts, and axe validation).
   */
  describe('Accessibility', () => {
    it('passes basic jest-axe audit', async () => {
      const { container } = render(<ConfigSampler />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('asserts ARIA tab configuration relationships', () => {
      render(<ConfigSampler />);
      const minimalTab = screen.getByRole('tab', { name: /^Minimal$/i });
      const minimalPanel = document.getElementById('panel-minimal');

      expect(minimalTab).toHaveAttribute('aria-controls', 'panel-minimal');
      expect(minimalPanel).toHaveAttribute('aria-labelledby', 'tab-minimal');
    });

    it('asserts knobs table header uses scope="col"', () => {
      render(<ConfigSampler />);
      const headers = screen.getAllByRole('columnheader');
      headers.forEach((th) => {
        expect(th).toHaveAttribute('scope', 'col');
      });
    });

    it('supports arrow-key and Home/End roving tabindex navigation', () => {
      render(<ConfigSampler />);
      const minimalTab = screen.getByRole('tab', { name: /^Minimal$/i });
      const fullTab = screen.getByRole('tab', { name: /Full-featured/i });
      const monorepoTab = screen.getByRole('tab', { name: /Monorepo with scope rules/i });

      minimalTab.focus();
      expect(minimalTab).toHaveFocus();

      // ArrowRight to Full-featured
      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
      expect(fullTab).toHaveAttribute('aria-selected', 'true');
      expect(fullTab).toHaveFocus();

      // ArrowRight to Monorepo
      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
      expect(monorepoTab).toHaveAttribute('aria-selected', 'true');
      expect(monorepoTab).toHaveFocus();

      // ArrowRight cycles back to Minimal
      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
      expect(minimalTab).toHaveAttribute('aria-selected', 'true');
      expect(minimalTab).toHaveFocus();

      // ArrowLeft to Monorepo
      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowLeft' });
      expect(monorepoTab).toHaveAttribute('aria-selected', 'true');
      expect(monorepoTab).toHaveFocus();

      // Home key moves to Minimal
      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'Home' });
      expect(minimalTab).toHaveAttribute('aria-selected', 'true');
      expect(minimalTab).toHaveFocus();

      // End key moves to Monorepo
      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'End' });
      expect(monorepoTab).toHaveAttribute('aria-selected', 'true');
      expect(monorepoTab).toHaveFocus();
    });
  });

  /**
   * Mobile responsive style check.
   */
  describe('Responsive/Mobile Styling', () => {
    it('verifies that the table wrapper uses horizontal overflow class', () => {
      const { container } = render(<ConfigSampler />);
      const wrapper = container.querySelector('div[class*="tableWrapper"]');
      expect(wrapper).toBeInTheDocument();
    });
  });

  /**
   * Regression snapshots to lock verbatim content.
   */
  describe('Regression: Content Snapshots', () => {
    it('matches snapshot for YAML content constants', () => {
      expect(MINIMAL_YAML).toMatchSnapshot();
      expect(FULL_YAML).toMatchSnapshot();
      expect(MONOREPO_YAML).toMatchSnapshot();
    });

    it('matches snapshot for general render tree', () => {
      const { container } = render(<ConfigSampler />);
      expect(container).toMatchSnapshot();
    });
  });
});
