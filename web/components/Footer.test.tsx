import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import Footer from './Footer';

describe('Footer Component', () => {
  it('renders brand and tagline', () => {
    render(<Footer />);
    expect(screen.getByText('Lychee')).toBeInTheDocument();
    expect(screen.getByText('Peel back your pull requests.')).toBeInTheDocument();
  });

  it('renders Docs and Project columns with correct links', () => {
    render(<Footer />);
    
    // Docs Column
    expect(screen.getByRole('heading', { name: 'Docs' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Getting Started' })).toHaveAttribute('href', '/docs/getting-started');
    expect(screen.getByRole('link', { name: 'Configuration' })).toHaveAttribute('href', '/docs/configuration');
    expect(screen.getByRole('link', { name: 'Commands' })).toHaveAttribute('href', '/docs/commands');
    expect(screen.getByRole('link', { name: 'Architecture' })).toHaveAttribute('href', '/docs/architecture');
    expect(screen.getByRole('link', { name: 'Deployment' })).toHaveAttribute('href', '/docs/deployment');

    // Project Column
    expect(screen.getByRole('heading', { name: 'Project' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'GitHub' })).toHaveAttribute('href', 'https://github.com/aspect-analytics/lychee');
    expect(screen.getByRole('link', { name: 'CHANGELOG' })).toHaveAttribute('href', 'https://github.com/aspect-analytics/lychee/blob/main/CHANGELOG.md');
    expect(screen.getByRole('link', { name: 'Roadmap' })).toHaveAttribute('href', '/docs/roadmap');
    expect(screen.getByRole('link', { name: 'Security' })).toHaveAttribute('href', '/docs/security');
    expect(screen.getByRole('link', { name: 'Glossary' })).toHaveAttribute('href', '/docs/glossary');
  });

  it('renders bottom bar elements', () => {
    render(<Footer version="v1.2.3" />);
    expect(screen.getByText('v1.2.3')).toBeInTheDocument();
    expect(screen.getByText('MIT License')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Spec' })).toHaveAttribute('href', '/docs');
  });

  it('defaults to v0.1.5 when no version is provided', () => {
    render(<Footer />);
    expect(screen.getByText('v0.1.5')).toBeInTheDocument();
  });

  it('renders reviewed by text', () => {
    render(<Footer />);
    expect(screen.getByText('Reviewed to the core by Lychee 🌴')).toBeInTheDocument();
  });
});
