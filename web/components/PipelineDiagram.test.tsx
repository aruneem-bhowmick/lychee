import React from 'react';
import { act, render, screen } from '@testing-library/react';
import PipelineDiagram, { PIPELINE_STAGES } from './PipelineDiagram';
import { axe, toHaveNoViolations } from 'jest-axe';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

expect.extend(toHaveNoViolations);

type ObserverCallback = (entries: Array<Partial<IntersectionObserverEntry>>) => void;

/** Minimal IntersectionObserver stand-in for triggering the pipeline's sequential reveal by hand. */
class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];
  callback: ObserverCallback;
  disconnect = () => {};

  constructor(callback: ObserverCallback) {
    this.callback = callback;
    MockIntersectionObserver.instances.push(this);
  }

  observe() {}
  unobserve() {}

  trigger(entries: Array<Partial<IntersectionObserverEntry>>) {
    this.callback(entries);
  }
}

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

  it('gives every stage card an increasing animation-delay by index, 80ms apart', () => {
    const { container } = render(<PipelineDiagram />);
    const cards = container.querySelectorAll<HTMLElement>('[data-stage-index]');

    cards.forEach((card, index) => {
      expect(card.style.animationDelay).toBe(`${index * 80}ms`);
    });
  });

  it('renders all stages fully visible before any intersection fires (static fallback)', () => {
    const { container } = render(<PipelineDiagram />);
    const list = container.querySelector('ol');
    expect(list?.className).not.toContain('inView');
  });

  describe('sequential reveal on scroll into view', () => {
    beforeEach(() => {
      MockIntersectionObserver.instances = [];
      (global as any).IntersectionObserver = MockIntersectionObserver;
    });

    afterEach(() => {
      delete (global as any).IntersectionObserver;
    });

    it('adds the inView class once the diagram intersects the viewport', () => {
      const { container } = render(<PipelineDiagram />);
      const list = container.querySelector('ol') as HTMLElement;
      const observer = MockIntersectionObserver.instances[0];

      act(() => {
        observer.trigger([{ isIntersecting: true, target: list }]);
      });

      expect(list.className).toContain('inView');
    });

    it('does not add the inView class on a non-intersecting entry', () => {
      const { container } = render(<PipelineDiagram />);
      const list = container.querySelector('ol') as HTMLElement;
      const observer = MockIntersectionObserver.instances[0];

      act(() => {
        observer.trigger([{ isIntersecting: false, target: list }]);
      });

      expect(list.className).not.toContain('inView');
    });
  });
});
