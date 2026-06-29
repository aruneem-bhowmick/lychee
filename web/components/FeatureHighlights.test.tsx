import React from 'react';
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import FeatureHighlights, { FEATURES } from './FeatureHighlights';

expect.extend(toHaveNoViolations);

describe('FeatureHighlights Component', () => {
  it('renders without crashing (smoke)', () => {
    render(<FeatureHighlights />);
    expect(screen.getByRole('heading', { level: 2, name: 'Why Lychee' })).toBeInTheDocument();
  });

  it('has exactly 5 features defined (unit)', () => {
    expect(FEATURES.length).toBe(5);
  });

  it('has correct titles in order (unit)', () => {
    const expectedTitles = [
      'Smart Model Tiering',
      'No-Spam Ergonomics',
      'Predictable Cost',
      'Map-Reduce for Large PRs',
      'Interactive Commands',
    ];
    const actualTitles = FEATURES.map((f) => f.title);
    expect(actualTitles).toEqual(expectedTitles);
  });

  it('has correct icons in order (unit)', () => {
    const expectedIcons = ['⚖️', '🔕', '💰', '🗂️', '💬'];
    const actualIcons = FEATURES.map((f) => f.icon);
    expect(actualIcons).toEqual(expectedIcons);
  });

  it('renders exactly 5 article elements (component)', () => {
    render(<FeatureHighlights />);
    const articles = screen.getAllByRole('article');
    expect(articles.length).toBe(5);
  });

  it('renders each card title as an h3 (component)', () => {
    render(<FeatureHighlights />);
    FEATURES.forEach((feature) => {
      expect(screen.getByRole('heading', { level: 3, name: feature.title })).toBeInTheDocument();
    });
  });

  it('contains specific text in Card 3 and Card 4 (component)', () => {
    render(<FeatureHighlights />);
    // Using string matching for exact substrings since backticks are rendered directly in text.
    expect(
      screen.getByText(
        (content, element) => content.includes('Set a `budget_cap_usd` in `.lychee.yml` and Lychee will halt and report a partial result rather than exceeding it.')
      )
    ).toBeInTheDocument();
    
    expect(
      screen.getByText(
        (content, element) => content.includes('partitions them into groups of 10')
      )
    ).toBeInTheDocument();
  });

  it('is accessible and has correct heading hierarchy (accessibility)', async () => {
    const { container } = render(<FeatureHighlights />);
    expect(screen.getByRole('heading', { level: 2 })).toBeInTheDocument();
    const h3s = screen.getAllByRole('heading', { level: 3 });
    expect(h3s.length).toBe(5);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('matches snapshot for all card bodies (regression)', () => {
    const bodies = FEATURES.map((f) => f.body);
    expect(bodies).toMatchSnapshot();
  });

  it('matches snapshot for full render (regression)', () => {
    const { container } = render(<FeatureHighlights />);
    expect(container).toMatchSnapshot();
  });

  it('satisfies sanity checks for exact figures and no banned words', () => {
    const fullText = FEATURES.map((f) => f.title + ' ' + f.body).join(' ');
    expect(fullText).not.toMatch(/phase/i);
    expect(fullText).not.toMatch(/LP-R/i);

    expect(FEATURES[0].body).toContain('100,000 characters');
    expect(FEATURES[1].body).toContain('SHA-256');
  });
});
