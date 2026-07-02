import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import ScrollReveal from './ScrollReveal';

expect.extend(toHaveNoViolations);

type ObserverCallback = (entries: Array<Partial<IntersectionObserverEntry>>) => void;

/** Minimal IntersectionObserver stand-in for triggering ScrollReveal's reveal transition by hand. */
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

describe('ScrollReveal', () => {
  beforeEach(() => {
    MockIntersectionObserver.instances = [];
    (global as any).IntersectionObserver = MockIntersectionObserver;
  });

  afterEach(() => {
    delete (global as any).IntersectionObserver;
  });

  it('renders children, visible by default, before any intersection fires', () => {
    render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    const text = screen.getByText('Revealed content');
    expect(text).toBeInTheDocument();
    expect(text.closest('div')).not.toHaveClass('revealed');
  });

  it('adds the revealed class after the wrapper intersects the viewport', () => {
    const { container } = render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    const wrapper = container.firstChild as HTMLElement;
    const observer = MockIntersectionObserver.instances[0];

    act(() => {
      observer.trigger([{ isIntersecting: true, target: wrapper }]);
    });

    expect(wrapper.className).toContain('revealed');
  });

  it('does not reveal on a non-intersecting entry', () => {
    const { container } = render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    const wrapper = container.firstChild as HTMLElement;
    const observer = MockIntersectionObserver.instances[0];

    act(() => {
      observer.trigger([{ isIntersecting: false, target: wrapper }]);
    });

    expect(wrapper.className).not.toContain('revealed');
  });

  it('renders the requested wrapper tag', () => {
    const { container } = render(
      <ScrollReveal as="section">
        <p>Revealed content</p>
      </ScrollReveal>
    );

    expect(container.querySelector('section')).toBeInTheDocument();
  });

  it('defaults to a div wrapper', () => {
    const { container } = render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    expect(container.firstElementChild?.tagName).toBe('DIV');
  });

  it('applies delayMs as an inline animation-delay style', () => {
    const { container } = render(
      <ScrollReveal delayMs={160}>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.animationDelay).toBe('160ms');
  });

  it('omits the animation-delay style when delayMs is 0 (the default)', () => {
    const { container } = render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.animationDelay).toBe('');
  });

  it('remains visible (no revealed class required) when IntersectionObserver is unavailable', () => {
    delete (global as any).IntersectionObserver;

    const { container } = render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    expect(screen.getByText('Revealed content')).toBeInTheDocument();
    expect((container.firstChild as HTMLElement).className).not.toContain('revealed');
  });

  it('disconnects the observer after the first reveal', () => {
    const { container } = render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    const wrapper = container.firstChild as HTMLElement;
    const observer = MockIntersectionObserver.instances[0];
    let disconnected = false;
    observer.disconnect = () => {
      disconnected = true;
    };

    act(() => {
      observer.trigger([{ isIntersecting: true, target: wrapper }]);
    });

    expect(disconnected).toBe(true);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <ScrollReveal>
        <h2>Section heading</h2>
        <p>Section body text.</p>
      </ScrollReveal>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('matches the snapshot before reveal', () => {
    const { container } = render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );
    expect(container).toMatchSnapshot();
  });

  it('matches the snapshot after reveal', () => {
    const { container } = render(
      <ScrollReveal>
        <p>Revealed content</p>
      </ScrollReveal>
    );

    const wrapper = container.firstChild as HTMLElement;
    const observer = MockIntersectionObserver.instances[0];
    act(() => {
      observer.trigger([{ isIntersecting: true, target: wrapper }]);
    });

    expect(container).toMatchSnapshot();
  });
});
