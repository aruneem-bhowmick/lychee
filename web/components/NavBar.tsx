'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import styles from './NavBar.module.css';
import { useScrollSpy } from '@/lib/useScrollSpy';

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
 * Landing page section ids observed for live scroll-spy highlighting, in
 * document order. `useScrollSpy` only observes ids actually present in the
 * DOM, so this list is safe to pass in on every route even though most
 * routes only render a subset (or none) of these sections.
 */
export const SCROLL_SPY_SECTION_IDS = [
  'hero',
  'features',
  'how-it-works',
  'setup',
  'output',
  'commands',
  'configure',
  'contribute',
] as const;

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
 * Splits an in-page anchor href into its path and hash parts, e.g.
 * `"/#setup"` becomes `{ path: "/", hash: "#setup" }`. Returns `null` for
 * links that aren't in-page anchors (no `#`), such as `/docs` or an
 * external URL — those should navigate normally rather than being
 * intercepted for smooth-scrolling.
 *
 * @param href - The link's href attribute.
 * @returns The parsed path/hash pair, or null if href has no hash.
 */
function parseAnchorHref(href: string): { path: string; hash: string } | null {
  const hashIndex = href.indexOf('#');
  if (hashIndex === -1) return null;
  return { path: href.slice(0, hashIndex) || '/', hash: href.slice(hashIndex) };
}

/**
 * NavBar component providing a fixed top navigation with a brand link,
 * desktop navigation links, and a mobile hamburger menu. When `activeId`
 * isn't explicitly provided, it falls back to a live scroll-spy reading so
 * the nav highlights the section currently in view on the landing page.
 * @param props Configuration props including custom links and active section ID.
 */
export default function NavBar({ links = DEFAULT_LINKS, activeId: activeIdProp }: NavBarProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const spyActiveId = useScrollSpy({ sectionIds: [...SCROLL_SPY_SECTION_IDS] });
  const activeId = activeIdProp ?? spyActiveId;

  const toggleMenu = () => setOpen((prev) => !prev);
  const closeMenu = () => setOpen(false);

  /**
   * Handles clicks on nav links. For an in-page anchor pointing at a
   * section on the current page, smoothly scrolls to it and updates the
   * URL hash instead of relying on the browser's default (instant) jump;
   * always closes the mobile menu. Links to other routes or external
   * sites are left to navigate normally.
   *
   * @param event - The click event on the anchor.
   * @param href - The anchor's href, as passed to the link.
   */
  const handleNavClick = (event: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    const parsed = parseAnchorHref(href);
    const target = parsed && typeof document !== 'undefined' ? document.getElementById(parsed.hash.slice(1)) : null;

    if (!parsed || typeof window === 'undefined' || window.location.pathname !== parsed.path || !target) {
      closeMenu();
      return;
    }

    event.preventDefault();
    if (typeof target.scrollIntoView === 'function') {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    window.history.pushState(null, '', parsed.hash);
    closeMenu();
  };

  return (
    <header className={styles.nav} role="banner">
      <div className={styles.inner}>
        <Link href="/#hero" className={styles.brand} onClick={(e) => handleNavClick(e, '/#hero')}>Lychee</Link>

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
                    onClick={(e) => handleNavClick(e, link.href)}
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
              onClick={(e) => handleNavClick(e, link.href)}
            >
              {link.label}
            </a>
          );
        })}
      </div>
    </header>
  );
}
