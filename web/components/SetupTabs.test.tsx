import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { axe, toHaveNoViolations } from 'jest-axe';

import SetupTabs, { WORKFLOW_YAML, DOCKER_BASH, LYCHEE_YML, PREREQS_TEXT, APP_REGISTER_TEXT, DIRECT_BASH } from './SetupTabs';
import SetupTabsClient from './SetupTabsClient';

expect.extend(toHaveNoViolations);

// Mock CodeBlock as it's an async server component
jest.mock('./CodeBlock', () => {
  return function MockCodeBlock({ code, filename, lang }: any) {
    return (
      <div data-testid="code-block" data-filename={filename} data-lang={lang}>
        {code}
      </div>
    );
  };
});

describe('SetupTabs Component & Constants', () => {
  describe('Unit: Constants', () => {
    it('asserts WORKFLOW_YAML contains specific strings', () => {
      expect(WORKFLOW_YAML).toContain('name: Lychee PR Review');
      expect(WORKFLOW_YAML).toContain('python scripts/run_action.py');
    });

    it('asserts DOCKER_BASH contains specific strings', () => {
      expect(DOCKER_BASH).toContain('-p 8000:8000');
    });
    
    it('asserts Regression: exact character sequences are preserved', () => {
      expect(LYCHEE_YML).toMatchSnapshot();
      expect(WORKFLOW_YAML).toMatchSnapshot();
      expect(DOCKER_BASH).toMatchSnapshot();
      expect(DIRECT_BASH).toMatchSnapshot();
      expect(PREREQS_TEXT).toMatchSnapshot();
      expect(APP_REGISTER_TEXT).toMatchSnapshot();
    });
  });

  describe('Component Behavior', () => {
    it('renders without crashing (smoke test)', () => {
      render(<SetupTabs />);
      expect(screen.getByRole('tablist')).toBeInTheDocument();
    });

    it('asserts two tabs and default selection', () => {
      render(<SetupTabs />);
      const actionsTab = screen.getByRole('tab', { name: /GitHub Actions/i });
      const appTab = screen.getByRole('tab', { name: /GitHub App/i });

      expect(actionsTab).toBeInTheDocument();
      expect(appTab).toBeInTheDocument();
      expect(actionsTab).toHaveAttribute('aria-selected', 'true');
      expect(appTab).toHaveAttribute('aria-selected', 'false');
    });

    it('asserts panels visibility and tab switching', () => {
      render(<SetupTabs />);
      
      const actionsPanel = document.getElementById('panel-github-actions');
      const appPanel = document.getElementById('panel-github-app');
      
      expect(actionsPanel).not.toHaveAttribute('hidden');
      expect(appPanel).toHaveAttribute('hidden');

      expect(actionsPanel).toHaveTextContent('Step 1: Prerequisites');
      expect(actionsPanel).toHaveTextContent('Step 5: Open a pull request');

      const appTab = screen.getByRole('tab', { name: /GitHub App/i });
      fireEvent.click(appTab);

      expect(appTab).toHaveAttribute('aria-selected', 'true');
      expect(actionsPanel).toHaveAttribute('hidden');
      expect(appPanel).not.toHaveAttribute('hidden');

      expect(appPanel).toHaveTextContent('Step 1: Register a GitHub App');
      expect(appPanel).toHaveTextContent('Step 5: Install the App on your repositories');
    });

    it('asserts the workflow CodeBlock shows filename', () => {
      render(<SetupTabs />);
      const codeBlocks = screen.getAllByTestId('code-block');
      const workflowBlock = codeBlocks.find(cb => cb.getAttribute('data-filename') === '.github/workflows/lychee-review.yml');
      expect(workflowBlock).toBeInTheDocument();
    });

    it('asserts target=_blank on Anthropic link', () => {
      render(<SetupTabs />);
      const link = screen.getByRole('link', { name: /https:\/\/console.anthropic.com/i });
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('asserts sanity checks for exact strings and links', () => {
      render(<SetupTabs />);
      
      // Step 3 secret name
      expect(screen.getByText('ANTHROPIC_API_KEY')).toBeInTheDocument();
      
      // Health-check note
      expect(screen.getByText(/GET \/health/)).toBeInTheDocument();
      
      // Step 5 Actions callout
      expect(screen.getByText(/Lychee will post a review comment automatically./)).toBeInTheDocument();
      
      // Configuration reference link
      const configLink = screen.getByRole('link', { name: /Configuration reference/i });
      expect(configLink).toHaveAttribute('href', '/docs/configuration');
      
      // Deployment CTA
      const deployLink = screen.getByRole('link', { name: /Full deployment guide/i });
      expect(deployLink).toHaveAttribute('href', '/docs/deployment');
      
      // Output CTA
      const outputLink = screen.getByRole('link', { name: /See what the output looks like/i });
      expect(outputLink).toHaveAttribute('href', '#output');
    });
  });

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = render(<SetupTabs />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('supports arrow-key navigation between tabs', () => {
      render(<SetupTabs />);
      const actionsTab = screen.getByRole('tab', { name: /GitHub Actions/i });
      const appTab = screen.getByRole('tab', { name: /GitHub App/i });

      actionsTab.focus();
      expect(actionsTab).toHaveFocus();

      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowRight' });
      expect(appTab).toHaveAttribute('aria-selected', 'true');
      expect(appTab).toHaveFocus();

      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'ArrowLeft' });
      expect(actionsTab).toHaveAttribute('aria-selected', 'true');
      expect(actionsTab).toHaveFocus();

      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'End' });
      expect(appTab).toHaveAttribute('aria-selected', 'true');
      expect(appTab).toHaveFocus();

      fireEvent.keyDown(screen.getByRole('tablist'), { key: 'Home' });
      expect(actionsTab).toHaveAttribute('aria-selected', 'true');
      expect(actionsTab).toHaveFocus();
    });
  });

  describe('Visual/Snapshot', () => {
    it('matches snapshot for panels output', () => {
      const { container } = render(<SetupTabs />);
      expect(container).toMatchSnapshot();
    });
  });
});
