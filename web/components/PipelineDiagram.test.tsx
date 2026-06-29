import React from 'react';
import { render, screen } from '@testing-library/react';
import PipelineDiagram, { PIPELINE_STAGES } from './PipelineDiagram';
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

describe('PipelineDiagram', () => {
  it('has exactly 7 stages', () => {
    expect(PIPELINE_STAGES).toHaveLength(7);
  });

  it('matches the exact seven stage strings in order', () => {
    const expectedLabels = [
      'PR Event',
      'Context Assembly (diff, files, commits, metadata)',
      'Triage Pass',
      'Model Selection (Haiku / Sonnet / Opus based on size + scope rules)',
      'Prompt Construction (persona + rubric + PR context + conventions)',
      'Claude API (structured tool call → ReviewResult)',
      'Render + Post (Nectar → The Peel → Pits → upsert comment)'
    ];

    PIPELINE_STAGES.forEach((stage, index) => {
      expect(stage.label).toBe(expectedLabels[index]);
    });
  });

  it('has exactly one optional stage which is Triage Pass', () => {
    const optionalStages = PIPELINE_STAGES.filter(stage => stage.optional);
    expect(optionalStages).toHaveLength(1);
    expect(optionalStages[0].label).toBe('Triage Pass');
  });

  it('renders all seven stage labels in order', () => {
    const { container } = render(<PipelineDiagram />);
    const labels = container.querySelectorAll('[class*="stageLabel"]');
    expect(labels).toHaveLength(7);
    
    PIPELINE_STAGES.forEach((stage, index) => {
      expect(labels[index]).toHaveTextContent(stage.label);
    });
  });

  it('shows an "Optional" annotation on the Triage stage', () => {
    render(<PipelineDiagram />);
    const triageBadge = screen.getByText('Optional', { selector: 'span' });
    expect(triageBadge).toBeInTheDocument();
  });

  it('renders as an ordered list for accessibility', () => {
    render(<PipelineDiagram />);
    const list = screen.getByRole('list');
    expect(list.tagName).toBe('OL');
  });

  it('passes accessibility tests', async () => {
    const { container } = render(<PipelineDiagram />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('matches snapshot', () => {
    const { container } = render(<PipelineDiagram />);
    expect(container).toMatchSnapshot();
  });
});
