import React from 'react';
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import Home, { dynamic } from './page';

expect.extend(toHaveNoViolations);

import { vi } from 'vitest';

// Mock `next/navigation` for `SetupTabs` and other components that might use it
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

// Mock CodeBlock which is an async Server Component and causes Promise rendering errors in tests
vi.mock('@/components/CodeBlock', () => ({
  default: () => <div data-testid="code-block-mock">CodeBlock Mock</div>
}));

describe('Landing Page Assembly (Home)', () => {
  it('exports force-static dynamic configuration', () => {
    expect(dynamic).toBe('force-static');
  });

  it('renders without crashing and displays canonical tagline', () => {
    render(<Home />);
    expect(screen.getByText(/Peel back your pull requests\./i)).toBeInTheDocument();
  });

  it('renders all eight content sections with the correct anchor IDs', () => {
    const { container } = render(<Home />);
    
    const requiredIds = [
      'hero',
      'features',
      'how-it-works',
      'setup',
      'output',
      'commands',
      'configure',
      'contribute'
    ];

    requiredIds.forEach(id => {
      const element = container.querySelector(`#${id}`);
      expect(element).toBeInTheDocument();
      expect(element?.tagName.toLowerCase()).toBe('section');
    });
  });

  it('renders sections in the correct order', () => {
    const { container } = render(<Home />);
    const sections = container.querySelectorAll('section[id]');
    const sectionIds = Array.from(sections).map(section => section.id);

    const expectedOrder = [
      'hero',
      'features',
      'how-it-works',
      'setup',
      'output',
      'commands',
      'configure',
      'contribute'
    ];

    expect(sectionIds).toEqual(expectedOrder);
  });

  it('has exactly one h1 element', () => {
    const { container } = render(<Home />);
    const h1Elements = container.querySelectorAll('h1');
    expect(h1Elements).toHaveLength(1);
  });

  it('does not have duplicate IDs', () => {
    const { container } = render(<Home />);
    const elementsWithId = container.querySelectorAll('[id]');
    const ids = Array.from(elementsWithId).map(el => el.id);
    
    const uniqueIds = new Set(ids);
    expect(ids.length).toBe(uniqueIds.size);
  });

  it('passes basic accessibility checks', async () => {
    const { container } = render(<Home />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 20000);
});
