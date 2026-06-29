import React from 'react';
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import FeatureCard from './FeatureCard';

expect.extend(toHaveNoViolations);

describe('FeatureCard Component', () => {
  const sampleProps = {
    icon: '🚀',
    title: 'Test Title',
    body: 'This is a test body paragraph.',
  };

  it('renders without crashing (smoke)', () => {
    render(<FeatureCard {...sampleProps} />);
    expect(screen.getByRole('article')).toBeInTheDocument();
  });

  it('renders icon, title, and body correctly', () => {
    render(<FeatureCard {...sampleProps} />);
    expect(screen.getByText('🚀')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Test Title' })).toBeInTheDocument();
    expect(screen.getByText('This is a test body paragraph.')).toBeInTheDocument();
  });

  it('is accessible', async () => {
    const { container } = render(<FeatureCard {...sampleProps} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('matches snapshot for regression', () => {
    const { container } = render(<FeatureCard {...sampleProps} />);
    expect(container).toMatchSnapshot();
  });
});
