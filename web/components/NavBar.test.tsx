import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import NavBar, { isActive, SCROLL_SPY_SECTION_IDS } from './NavBar';

type ObserverCallback = (entries: Array<Partial<IntersectionObserverEntry>>) => void;

/** Minimal IntersectionObserver stand-in for exercising NavBar's internal useScrollSpy wiring. */
class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = [];
  callback: ObserverCallback;

  constructor(callback: ObserverCallback) {
    this.callback = callback;
    MockIntersectionObserver.instances.push(this);
  }

  observe() {}
  unobserve() {}
  disconnect() {}

  trigger(entries: Array<Partial<IntersectionObserverEntry>>) {
    this.callback(entries);
  }
}

describe('NavBar Component', () => {
  describe('isActive helper', () => {
    it('returns true when activeId matches the href', () => {
      expect(isActive('/#setup', 'setup')).toBe(true);
    });

    it('returns false when activeId does not match the href', () => {
      expect(isActive('/docs', 'setup')).toBe(false);
      expect(isActive('/#how-it-works', 'setup')).toBe(false);
    });

    it('returns false when activeId is undefined', () => {
      expect(isActive('/#setup')).toBe(false);
    });
  });

  describe('rendering and interaction', () => {
    it('renders the brand link with correct href', () => {
      render(<NavBar />);
      const brand = screen.getByText('Lychee');
      expect(brand).toHaveAttribute('href', '/#hero');
    });

    it('renders all default links with correct hrefs', () => {
      render(<NavBar />);
      // We can query by role for navigation links
      
      const howItWorks = screen.getAllByRole('link', { name: 'How It Works' })[0];
      expect(howItWorks).toHaveAttribute('href', '/#how-it-works');

      const setup = screen.getAllByRole('link', { name: 'Setup' })[0];
      expect(setup).toHaveAttribute('href', '/#setup');

      const docs = screen.getAllByRole('link', { name: 'Docs' })[0];
      expect(docs).toHaveAttribute('href', '/docs');

      const contribute = screen.getAllByRole('link', { name: 'Contribute' })[0];
      expect(contribute).toHaveAttribute('href', '/#contribute');

      const github = screen.getAllByRole('link', { name: 'GitHub ↗' })[0];
      expect(github).toHaveAttribute('href', 'https://github.com/aspect-analytics/lychee');
      expect(github).toHaveAttribute('target', '_blank');
      expect(github).toHaveAttribute('rel', 'noopener noreferrer');
    });

    it('toggles mobile menu on hamburger click', () => {
      render(<NavBar />);
      
      const button = screen.getByLabelText('Toggle navigation menu');
      expect(button).toHaveAttribute('aria-expanded', 'false');

      fireEvent.click(button);
      expect(button).toHaveAttribute('aria-expanded', 'true');

      // Click a link to close the menu
      const links = screen.getAllByRole('link', { name: 'Setup' });
      const mobileLink = links[1]; // The second one is the mobile menu link
      fireEvent.click(mobileLink);

      expect(button).toHaveAttribute('aria-expanded', 'false');
    });
  });

  describe('scroll-spy section ids (Sanity)', () => {
    it('observes the eight landing sections in document order', () => {
      expect(SCROLL_SPY_SECTION_IDS).toEqual([
        'hero',
        'features',
        'how-it-works',
        'setup',
        'output',
        'commands',
        'configure',
        'contribute',
      ]);
    });
  });

  describe('active link highlighting', () => {
    it('marks the matching link active with aria-current and the active class when activeId is provided', () => {
      render(<NavBar activeId="setup" />);
      const setupLink = screen.getAllByRole('link', { name: 'Setup' })[0];

      expect(setupLink).toHaveAttribute('aria-current', 'true');
      expect(setupLink.className).toContain('active');
    });

    it('leaves all links inactive when activeId does not match any of them', () => {
      render(<NavBar activeId="hero" />);
      const links = screen.getAllByRole('link');

      links.forEach((link) => {
        expect(link).not.toHaveAttribute('aria-current');
      });
    });

    it('an explicit activeId prop takes precedence over the live scroll-spy reading', () => {
      // No IntersectionObserver in this test, so the internal hook would
      // otherwise report no active section at all.
      render(<NavBar activeId="how-it-works" />);
      const link = screen.getAllByRole('link', { name: 'How It Works' })[0];
      expect(link).toHaveAttribute('aria-current', 'true');
    });
  });

  describe('live scroll-spy wiring (no explicit activeId)', () => {
    beforeEach(() => {
      MockIntersectionObserver.instances = [];
      (global as any).IntersectionObserver = MockIntersectionObserver;
    });

    afterEach(() => {
      document.getElementById('setup')?.remove();
      delete (global as any).IntersectionObserver;
    });

    it('highlights the link for whichever section useScrollSpy reports active', () => {
      const section = document.createElement('div');
      section.id = 'setup';
      document.body.appendChild(section);

      render(<NavBar />);
      const setupLink = screen.getAllByRole('link', { name: 'Setup' })[0];
      expect(setupLink).not.toHaveAttribute('aria-current');

      const observer = MockIntersectionObserver.instances[0];
      act(() => {
        observer.trigger([{ isIntersecting: true, intersectionRatio: 1, target: section }]);
      });

      expect(setupLink).toHaveAttribute('aria-current', 'true');
    });
  });

  describe('smooth-scroll anchor handling', () => {
    afterEach(() => {
      document.getElementById('setup')?.remove();
      window.history.pushState(null, '', '/');
      // Element.prototype.scrollIntoView is a single persistent vi.fn()
      // installed once in vitest.setup.ts; vi.spyOn on an already-mocked
      // property returns that same mock rather than wrapping it, so only
      // clearing (not just restoring) it here keeps each test's call
      // count isolated from the others.
      vi.clearAllMocks();
    });

    it('scrolls the target section into view and updates the hash when the section exists on the page', () => {
      const section = document.createElement('div');
      section.id = 'setup';
      document.body.appendChild(section);
      const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView');

      render(<NavBar />);
      const setupLink = screen.getAllByRole('link', { name: 'Setup' })[0];
      fireEvent.click(setupLink);

      expect(scrollSpy).toHaveBeenCalledWith(expect.objectContaining({ behavior: 'smooth' }));
      expect(window.location.hash).toBe('#setup');
    });

    it('does not intercept the click when the target section is not on the page', () => {
      const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView');

      render(<NavBar />);
      const setupLink = screen.getAllByRole('link', { name: 'Setup' })[0];
      fireEvent.click(setupLink);

      expect(scrollSpy).not.toHaveBeenCalled();
      expect(window.location.hash).toBe('');
    });

    it('does not intercept clicks on external links', () => {
      const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView');

      render(<NavBar />);
      const githubLink = screen.getAllByRole('link', { name: 'GitHub ↗' })[0];
      fireEvent.click(githubLink);

      expect(scrollSpy).not.toHaveBeenCalled();
    });

    it('does not intercept clicks on links to other routes', () => {
      const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView');

      render(<NavBar />);
      const docsLink = screen.getAllByRole('link', { name: 'Docs' })[0];
      fireEvent.click(docsLink);

      expect(scrollSpy).not.toHaveBeenCalled();
    });
  });
});
