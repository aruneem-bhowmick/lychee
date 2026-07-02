import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useScrollSpy } from './useScrollSpy';

type ObserverCallback = (entries: Array<Partial<IntersectionObserverEntry>>) => void;

/** A minimal IntersectionObserver stand-in that records its wiring and lets tests fire entries by hand. */
class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];
  callback: ObserverCallback;
  options: IntersectionObserverInit | undefined;
  observed: Element[] = [];
  disconnect = vi.fn();

  constructor(callback: ObserverCallback, options?: IntersectionObserverInit) {
    this.callback = callback;
    this.options = options;
    MockIntersectionObserver.instances.push(this);
  }

  observe(el: Element) {
    this.observed.push(el);
  }

  unobserve = vi.fn();

  /** Simulates the browser invoking the observer callback with the given entries. */
  trigger(entries: Array<Partial<IntersectionObserverEntry>>) {
    this.callback(entries);
  }
}

const SECTION_IDS = ['hero', 'features', 'setup'];

/** Appends an empty element for each id to the document body, for the observer to find. */
function mountSections(ids: string[]): void {
  ids.forEach((id) => {
    const el = document.createElement('div');
    el.id = id;
    document.body.appendChild(el);
  });
}

/** Removes any section elements mountSections added, for test cleanup. */
function clearSections(): void {
  SECTION_IDS.forEach((id) => document.getElementById(id)?.remove());
}

describe('useScrollSpy', () => {
  beforeEach(() => {
    MockIntersectionObserver.instances = [];
    (global as any).IntersectionObserver = MockIntersectionObserver;
  });

  afterEach(() => {
    clearSections();
    delete (global as any).IntersectionObserver;
  });

  it('returns the first section id initially', () => {
    mountSections(SECTION_IDS);
    const { result } = renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS }));
    expect(result.current).toBe('hero');
  });

  it('updates to the most-visible section when it intersects', () => {
    mountSections(SECTION_IDS);
    const { result } = renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS }));

    const observer = MockIntersectionObserver.instances[0];
    const featuresEl = document.getElementById('features')!;

    act(() => {
      observer.trigger([
        { isIntersecting: true, intersectionRatio: 0.8, target: featuresEl },
      ]);
    });

    expect(result.current).toBe('features');
  });

  it('picks the entry with the highest intersection ratio among several intersecting at once', () => {
    mountSections(SECTION_IDS);
    const { result } = renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS }));

    const observer = MockIntersectionObserver.instances[0];
    const featuresEl = document.getElementById('features')!;
    const setupEl = document.getElementById('setup')!;

    act(() => {
      observer.trigger([
        { isIntersecting: true, intersectionRatio: 0.3, target: featuresEl },
        { isIntersecting: true, intersectionRatio: 0.9, target: setupEl },
      ]);
    });

    expect(result.current).toBe('setup');
  });

  it('ignores non-intersecting entries', () => {
    mountSections(SECTION_IDS);
    const { result } = renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS }));

    const observer = MockIntersectionObserver.instances[0];
    const featuresEl = document.getElementById('features')!;

    act(() => {
      observer.trigger([{ isIntersecting: false, intersectionRatio: 0, target: featuresEl }]);
    });

    expect(result.current).toBe('hero');
  });

  it('only observes ids that exist in the DOM, and does not set up an observer when none do', () => {
    const { result } = renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS }));

    expect(MockIntersectionObserver.instances).toHaveLength(0);
    expect(result.current).toBe('hero');
  });

  it('passes a custom rootMargin through to the observer, defaulting to a center-biased band', () => {
    mountSections(SECTION_IDS);
    renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS }));
    expect(MockIntersectionObserver.instances[0].options?.rootMargin).toBe('-45% 0px -45% 0px');

    MockIntersectionObserver.instances = [];
    renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS, rootMargin: '0px' }));
    expect(MockIntersectionObserver.instances[0].options?.rootMargin).toBe('0px');
  });

  it('disconnects the observer on unmount', () => {
    mountSections(SECTION_IDS);
    const { unmount } = renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS }));
    const observer = MockIntersectionObserver.instances[0];

    unmount();

    expect(observer.disconnect).toHaveBeenCalledTimes(1);
  });

  it('does not throw and returns the first id when IntersectionObserver is unavailable', () => {
    delete (global as any).IntersectionObserver;
    mountSections(SECTION_IDS);

    const { result } = renderHook(() => useScrollSpy({ sectionIds: SECTION_IDS }));

    expect(result.current).toBe('hero');
  });
});
