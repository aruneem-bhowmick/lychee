import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import NavBar, { isActive } from './NavBar';

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
});
