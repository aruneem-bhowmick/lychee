import React from 'react';
import { render, screen } from '@testing-library/react';
import HowItWorks, { DEPLOYMENT_ROWS } from './HowItWorks';
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

describe('HowItWorks', () => {
  it('has exactly 6 deployment rows with expected labels', () => {
    expect(DEPLOYMENT_ROWS).toHaveLength(6);
    const expectedLabels = ['Trigger', 'Infrastructure', 'State', 'Scale', 'Auth', 'Entry point'];
    
    DEPLOYMENT_ROWS.forEach((row, index) => {
      expect(row.label).toBe(expectedLabels[index]);
    });
  });

  it('renders the comparison table with two column headers', () => {
    render(<HowItWorks />);
    expect(screen.getByRole('columnheader', { name: 'CLI Mode (GitHub Actions)' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Server Mode (GitHub App)' })).toBeInTheDocument();
  });

  it('renders the State row correctly', () => {
    render(<HowItWorks />);
    const stateRowHeader = screen.getByRole('rowheader', { name: 'State' });
    const row = stateRowHeader.closest('tr');
    expect(row).toHaveTextContent('Stateless');
    expect(row).toHaveTextContent('SQLite (per-PR SHA + comment ID)');
  });

  it('shows Entry point row with run_action.py and run_server.py', () => {
    render(<HowItWorks />);
    const entryRowHeader = screen.getByRole('rowheader', { name: 'Entry point' });
    const row = entryRowHeader.closest('tr');
    expect(row).toHaveTextContent('scripts/run_action.py');
    expect(row).toHaveTextContent('scripts/run_server.py');
  });

  it('shows Auth row CLI cell containing GITHUB_TOKEN and ANTHROPIC_API_KEY', () => {
    render(<HowItWorks />);
    const authRowHeader = screen.getByRole('rowheader', { name: 'Auth' });
    const row = authRowHeader.closest('tr');
    expect(row).toHaveTextContent('GITHUB_TOKEN (auto) + ANTHROPIC_API_KEY');
  });

  it('renders the note about identical output', () => {
    render(<HowItWorks />);
    expect(screen.getByText('Both modes run the same review engine and produce identical output.')).toBeInTheDocument();
  });

  it('renders a CTA linking to /docs/architecture', () => {
    render(<HowItWorks />);
    const link = screen.getByRole('link', { name: /See the full architecture/i });
    expect(link).toHaveAttribute('href', '/docs/architecture');
  });

  it('renders without crashing (smoke test)', () => {
    const { container } = render(<HowItWorks />);
    expect(container).toBeInTheDocument();
  });

  it('uses table elements properly (th scope col/row)', () => {
    const { container } = render(<HowItWorks />);
    const colHeaders = container.querySelectorAll('th[scope="col"]');
    expect(colHeaders.length).toBe(3); // blank, CLI, Server
    
    const rowHeaders = container.querySelectorAll('th[scope="row"]');
    expect(rowHeaders.length).toBe(6);
  });

  it('passes accessibility tests', async () => {
    const { container } = render(<HowItWorks />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('matches snapshot for regression locking', () => {
    const { container } = render(<HowItWorks />);
    expect(container).toMatchSnapshot();
  });
});
