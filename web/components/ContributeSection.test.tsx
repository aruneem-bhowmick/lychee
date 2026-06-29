import React from 'react';
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { vi } from 'vitest';
import ContributeSection, { STANDARDS } from './ContributeSection';
import styles from './ContributeSection.module.css';

vi.mock('./CodeBlock', () => {
  return {
    default: function MockCodeBlock({ code, lang }: { code: string; lang: string }) {
      return <div data-testid="code-block" data-lang={lang}>{code}</div>;
    }
  };
});

expect.extend(toHaveNoViolations);

describe('ContributeSection Component', () => {
  describe('Unit Tests', () => {
    it('asserts STANDARDS.length === 6 and specific order/values', () => {
      expect(STANDARDS.length).toBe(6);
      
      const expectedStandards = [
        'Type annotations (strict)',
        'Linting',
        'Formatting',
        'Immutable models',
        'Pure functions for prompt & render',
        'No global state'
      ];
      
      expectedStandards.forEach((std, idx) => {
        expect(STANDARDS[idx].standard).toBe(std);
      });
      
      expect(STANDARDS[0].enforcedBy).toBe('mypy --strict');
    });
  });

  describe('Component Tests', () => {
    it('renders Step 1 clone and install commands verbatim', () => {
      render(<ContributeSection />);
      expect(screen.getByText(/git clone https:\/\/github\.com\/aspect-analytics\/lychee\.git/)).toBeInTheDocument();
      expect(screen.getByText(/pip install -e "\.\[dev\]"/)).toBeInTheDocument();
      expect(screen.getByText(/# Windows: \.venv\\Scripts\\activate/)).toBeInTheDocument();
    });

    it('renders Step 2 test suite instructions verbatim', () => {
      render(<ContributeSection />);
      expect(screen.getByText(/Coverage is enforced at 80% \(branch coverage\)\./)).toBeInTheDocument();
      expect(screen.getByText(/pytest --snapshot-update/)).toBeInTheDocument();
    });

    it('renders workflow items including dry-run command verbatim', () => {
      render(<ContributeSection />);
      const listItems = screen.getAllByRole('listitem');
      expect(listItems.length).toBe(4);
      expect(screen.getByText(/lychee review --dry-run --fixture tests\/fixtures\/pr_payload\.json/)).toBeInTheDocument();
    });

    it('renders security notice verbatim', () => {
      render(<ContributeSection />);
      expect(screen.getByText(/We acknowledge within 48 hours and provide a fix timeline within 7 days\./)).toBeInTheDocument();
    });

    it('renders CTAs to development and roadmap pages', () => {
      render(<ContributeSection />);
      const devLink = screen.getByRole('link', { name: /Development guide →/i });
      const roadmapLink = screen.getByRole('link', { name: /Roadmap →/i });
      expect(devLink).toHaveAttribute('href', '/docs/development');
      expect(roadmapLink).toHaveAttribute('href', '/docs/roadmap');
    });
  });

  describe('Accessibility Tests', () => {
    it('should have no axe violations', async () => {
      const { container } = render(<ContributeSection />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('uses th elements with scope="col"', () => {
      render(<ContributeSection />);
      const headers = screen.getAllByRole('columnheader');
      headers.forEach(th => {
        expect(th).toHaveAttribute('scope', 'col');
      });
    });

    it('labels the security notice as a landmark/region', () => {
      render(<ContributeSection />);
      const aside = screen.getByRole('complementary', { name: 'Security reporting' });
      expect(aside).toBeInTheDocument();
    });
  });

  describe('Smoke Test', () => {
    it('renders without crashing', () => {
      const { container } = render(<ContributeSection />);
      expect(container).toBeInTheDocument();
    });
  });

  describe('Sanity Tests', () => {
    it('renders the CI line verbatim', () => {
      render(<ContributeSection />);
      expect(screen.getByText('CI runs lint → type-check → engine integrity hash → test on every PR. All gates must be green before merge.')).toBeInTheDocument();
    });

    it('links to Canary Setup properly', () => {
      render(<ContributeSection />);
      const canaryLink = screen.getByRole('link', { name: /Canary Setup/i });
      expect(canaryLink).toHaveAttribute('href', '/docs/canary-setup');
    });

    it('includes Windows activation comment', () => {
      render(<ContributeSection />);
      expect(screen.getByText(/# Windows: \.venv\\Scripts\\activate/)).toBeInTheDocument();
    });
  });

  describe('Regression Test', () => {
    it('matches snapshot', () => {
      const { container } = render(<ContributeSection />);
      expect(container).toMatchSnapshot();
    });
  });

  describe('Responsive Tests', () => {
    it('wraps the standards table in a wrapper with overflow-x auto', () => {
      render(<ContributeSection />);
      const table = screen.getByRole('table');
      const wrapper = table.parentElement;
      expect(wrapper).toHaveClass(styles.tableWrapper);
    });
  });
});
