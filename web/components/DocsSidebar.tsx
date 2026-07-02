'use client';

import React, { useState } from 'react';
import styles from './DocsSidebar.module.css';

/** A single link in the docs sidebar. */
export interface SidebarItem {
  slug: string;
  label: string;
}

/** A group of sidebar items, visually separated from other groups by a divider. */
export interface SidebarGroup {
  items: SidebarItem[];
}

export interface DocsSidebarProps {
  /** Grouped nav items. Defaults to the canonical docs grouping. */
  groups?: SidebarGroup[];
  /** The slug of the doc currently being viewed, for highlighting. */
  activeSlug: string;
}

const DEFAULT_GROUPS: SidebarGroup[] = [
  {
    items: [
      { slug: 'getting-started', label: 'Getting Started' },
      { slug: 'configuration', label: 'Configuration' },
      { slug: 'commands', label: 'Commands' },
    ],
  },
  {
    items: [
      { slug: 'architecture', label: 'Architecture' },
      { slug: 'glossary', label: 'Glossary' },
    ],
  },
  {
    items: [
      { slug: 'deployment', label: 'Deployment' },
      { slug: 'security', label: 'Security' },
      { slug: 'canary-setup', label: 'Canary Setup' },
      { slug: 'api-reference', label: 'API Reference' },
    ],
  },
  {
    items: [
      { slug: 'development', label: 'Development' },
      { slug: 'roadmap', label: 'Roadmap' },
    ],
  },
];

/**
 * Grouped documentation sidebar. Renders as a persistent column on desktop
 * and collapses to a keyboard-operable drawer behind a toggle button on
 * mobile. The item matching `activeSlug` is marked with `aria-current`.
 *
 * @param props - Sidebar configuration.
 * @returns The rendered sidebar nav.
 */
export default function DocsSidebar({
  groups = DEFAULT_GROUPS,
  activeSlug,
}: DocsSidebarProps): JSX.Element {
  const [open, setOpen] = useState(false);

  return (
    <div className={styles.wrapper}>
      <button
        type="button"
        className={styles.toggle}
        aria-expanded={open}
        aria-controls="docs-sidebar-nav"
        onClick={() => setOpen((prev) => !prev)}
      >
        {open ? 'Close menu' : 'Browse docs'}
      </button>
      <nav
        id="docs-sidebar-nav"
        aria-label="Documentation"
        className={`${styles.sidebar} ${open ? styles.open : ''}`}
      >
        {groups.map((group, groupIndex) => (
          <React.Fragment key={group.items[0]?.slug ?? groupIndex}>
            {groupIndex > 0 && <hr className={styles.divider} />}
            <ul className={styles.list}>
              {group.items.map((item) => {
                const active = item.slug === activeSlug;
                return (
                  <li key={item.slug}>
                    <a
                      href={`/docs/${item.slug}`}
                      className={`${styles.link} ${active ? styles.active : ''}`}
                      aria-current={active ? 'page' : undefined}
                    >
                      {item.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </React.Fragment>
        ))}
      </nav>
    </div>
  );
}
