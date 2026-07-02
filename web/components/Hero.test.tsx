import React from 'react';
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import Hero from './Hero';

expect.extend(toHaveNoViolations);

describe('Hero Component', () => {
  it('renders the <h1> with exactly the canonical tagline', () => {
    render(<Hero />);
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading.textContent).toBe('Peel back your pull requests.');
  });

  it('renders the value proposition verbatim', () => {
    render(<Hero />);
    const text = screen.getByText('Self-hosted, Claude-powered PR reviews that run concurrently, report cost to the cent, and never post twice.');
    expect(text).toBeInTheDocument();
  });

  it('renders three canonical badges with correct labels and emojis', () => {
    render(<Hero />);
    const ripeBadge = screen.getByText('🟢 Ripe');
    const unripeBadge = screen.getByText('🟡 Unripe');
    const sourBadge = screen.getByText('🔴 Sour');

    expect(ripeBadge).toBeInTheDocument();
    expect(unripeBadge).toBeInTheDocument();
    expect(sourBadge).toBeInTheDocument();
  });

  it('renders the primary CTA linking to /#setup', () => {
    render(<Hero />);
    const link = screen.getByRole('link', { name: 'Get Started' });
    expect(link).toHaveAttribute('href', '/#setup');
  });

  it('renders the secondary CTA linking to the GitHub repo with target _blank', () => {
    render(<Hero />);
    const link = screen.getByRole('link', { name: 'View on GitHub' });
    expect(link).toHaveAttribute('href', 'https://github.com/aspect-analytics/lychee');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('has no accessibility violations and contains exactly one <h1>', async () => {
    const { container } = render(<Hero />);
    
    // Assert exactly one h1
    const h1s = container.querySelectorAll('h1');
    expect(h1s.length).toBe(1);

    // Assert alt text on the logo
    const logo = screen.getByAltText('Lychee');
    expect(logo).toBeInTheDocument();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('does not contain any banned words or explanatory sentences in badges', () => {
    const { container } = render(<Hero />);
    const html = container.innerHTML.toLowerCase();
    
    // Banned words check
    expect(html).not.toContain('powerful');
    expect(html).not.toContain('seamless');
    expect(html).not.toContain('easy to use');
  });

  it('matches the snapshot for regression locking', () => {
    const { container } = render(<Hero />);
    expect(container).toMatchSnapshot();
  });

  it('applies the one-shot badge-pulse animation class to every badge', () => {
    render(<Hero />);
    ['🟢 Ripe', '🟡 Unripe', '🔴 Sour'].forEach((label) => {
      expect(screen.getByText(label)).toHaveClass('badge-pulse');
    });
  });
});
