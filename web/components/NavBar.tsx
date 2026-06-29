'use client';

import React, { useState } from 'react';
import styles from './NavBar.module.css';

/**
 * Represents a single navigation link in the NavBar.
 */
export interface NavLink {
  label: string;
  href: string;
  external?: boolean;
}

/**
 * Props for the NavBar component.
 */
export interface NavBarProps {
  /** Array of links to display. Defaults to standard landing page links. */
  links?: NavLink[];
  /** Optional ID of the currently active section for scroll-spy highlighting. */
  activeId?: string;
}

const DEFAULT_LINKS: NavLink[] = [
  { label: 'How It Works', href: '/#how-it-works' },
  { label: 'Setup', href: '/#setup' },
  { label: 'Docs', href: '/docs' },
  { label: 'Contribute', href: '/#contribute' },
  { label: 'GitHub ↗', href: 'https://github.com/aspect-analytics/lychee', external: true },
];

/**
 * Determines whether a given link is currently active based on the activeId.
 * @param href The link's URL.
 * @param activeId The ID of the currently active section.
 * @returns True if the link targets the active section, false otherwise.
 */
export function isActive(href: string, activeId?: string): boolean {
  if (!activeId) return false;
  return href === `/#${activeId}`;
}

/**
 * NavBar component providing a fixed top navigation with a brand link,
 * desktop navigation links, and a mobile hamburger menu.
 * @param props Configuration props including custom links and active section ID.
 */
export default function NavBar({ links = DEFAULT_LINKS, activeId }: NavBarProps): JSX.Element {
  const [open, setOpen] = useState(false);

  const toggleMenu = () => setOpen((prev) => !prev);
  const closeMenu = () => setOpen(false);

  return (
    <header className={styles.nav} role="banner">
      <div className={styles.inner}>
        <a href="/#hero" className={styles.brand} onClick={closeMenu}>Lychee</a>
        
        <nav aria-label="Primary" className={styles.desktopNav}>
          <ul className={styles.navList}>
            {links.map((link) => {
              const active = isActive(link.href, activeId);
              return (
                <li key={link.label}>
                  <a
                    href={link.href}
                    className={`${styles.navLink} ${active ? styles.active : ''}`}
                    target={link.external ? '_blank' : undefined}
                    rel={link.external ? 'noopener noreferrer' : undefined}
                    aria-current={active ? 'true' : undefined}
                  >
                    {link.label}
                  </a>
                </li>
              );
            })}
          </ul>
        </nav>

        <button
          className={styles.menuToggle}
          aria-label="Toggle navigation menu"
          aria-expanded={open}
          aria-controls="mobile-menu"
          onClick={toggleMenu}
        >
          ☰
        </button>
      </div>

      <div id="mobile-menu" className={`${styles.mobileMenu} ${open ? styles.open : ''}`}>
        {links.map((link) => {
          const active = isActive(link.href, activeId);
          return (
            <a
              key={link.label}
              href={link.href}
              className={`${styles.navLink} ${active ? styles.active : ''}`}
              target={link.external ? '_blank' : undefined}
              rel={link.external ? 'noopener noreferrer' : undefined}
              aria-current={active ? 'true' : undefined}
              onClick={closeMenu}
            >
              {link.label}
            </a>
          );
        })}
      </div>
    </header>
  );
}
