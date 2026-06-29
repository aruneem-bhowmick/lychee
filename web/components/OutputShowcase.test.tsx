import React from 'react';
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import OutputShowcase, { PITS_DATA } from './OutputShowcase';

expect.extend(toHaveNoViolations);

describe('OutputShowcase', () => {
  describe('Unit tests', () => {
    it('should have 3 PitRows in order critical, major, minor with respective categories', () => {
      expect(PITS_DATA).toHaveLength(3);
      expect(PITS_DATA[0].severity).toBe('critical');
      expect(PITS_DATA[0].category).toBe('security');
      
      expect(PITS_DATA[1].severity).toBe('major');
      expect(PITS_DATA[1].category).toBe('correctness');
      
      expect(PITS_DATA[2].severity).toBe('minor');
      expect(PITS_DATA[2].category).toBe('tests');
    });
  });

  describe('Component tests', () => {
    it('renders all required elements and literal text verbatim', () => {
      render(<OutputShowcase />);
      
      // Header line
      expect(screen.getByText('🌴 Lychee peeled this PR · claude-sonnet-4-6')).toBeInTheDocument();
      
      // Literal comment text
      expect(screen.getByText('<!-- lychee:review -->')).toBeInTheDocument();
      
      // Ripeness pill
      expect(screen.getByText('🟡 Unripe')).toBeInTheDocument();
      
      // Nectar paragraph content
      const nectarText = screen.getByText(/critical security gap in webhook signature verification/);
      expect(nectarText).toBeInTheDocument();
      
      // Peel list
      const peelList = screen.getAllByRole('listitem');
      expect(peelList).toHaveLength(3);
      expect(screen.getByText('src/webhooks/stripe.py')).toBeInTheDocument();
      
      // Pits table
      const rows = screen.getAllByRole('row');
      expect(rows).toHaveLength(4); // 1 header + 3 data rows
      
      // Footer text
      const footerRegex = /Tokens: 4,821 in · 612 out · \$0\.023 · Reviewed to the core by Lychee 🌴/;
      expect(screen.getByText(footerRegex)).toBeInTheDocument();
      
      // Glossary link
      const glossaryLink = screen.getByRole('link', { name: /Glossary/ });
      expect(glossaryLink).toHaveAttribute('href', '/docs/glossary');
    });
  });

  describe('Visual/Snapshot tests', () => {
    it('matches the snapshot to lock the mock and annotations', () => {
      const { container } = render(<OutputShowcase />);
      expect(container).toMatchSnapshot();
    });
  });

  describe('Accessibility tests', () => {
    it('should have no axe accessibility violations', async () => {
      const { container } = render(<OutputShowcase />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('asserts the Pits table uses <th> headers', () => {
      render(<OutputShowcase />);
      const headers = screen.getAllByRole('columnheader');
      expect(headers).toHaveLength(3);
      expect(headers[0]).toHaveTextContent('Severity');
      expect(headers[1]).toHaveTextContent('Category');
      expect(headers[2]).toHaveTextContent('Finding');
    });
    
    it('asserts annotation labels are present as text elements', () => {
      render(<OutputShowcase />);
      // Just confirming they are in the document text, not just title attributes.
      expect(screen.getByText('Ripeness verdict: Ripe / Unripe / Sour')).toBeInTheDocument();
      expect(screen.getByText('Nectar — the distilled summary')).toBeInTheDocument();
      expect(screen.getByText('The Peel — file-by-file walkthrough')).toBeInTheDocument();
      expect(screen.getByText('Pits — findings with severity & category')).toBeInTheDocument();
      expect(screen.getByText('Cost footer — exact token usage and USD cost')).toBeInTheDocument();
    });
  });

  describe('Smoke tests', () => {
    it('renders without crashing', () => {
      expect(() => render(<OutputShowcase />)).not.toThrow();
    });
  });

  describe('Sanity tests', () => {
    it('asserts all five annotation labels render verbatim and cost figures match exactly', () => {
      render(<OutputShowcase />);
      expect(screen.getByText('Ripeness verdict: Ripe / Unripe / Sour')).toBeInTheDocument();
      expect(screen.getByText('Nectar — the distilled summary')).toBeInTheDocument();
      expect(screen.getByText('The Peel — file-by-file walkthrough')).toBeInTheDocument();
      expect(screen.getByText('Pits — findings with severity & category')).toBeInTheDocument();
      expect(screen.getByText('Cost footer — exact token usage and USD cost')).toBeInTheDocument();
      
      const footerRegex = /Tokens: 4,821 in · 612 out · \$0\.023 · Reviewed to the core by Lychee 🌴/;
      expect(screen.getByText(footerRegex)).toBeInTheDocument();
    });
  });
});
