'use client';

import React, { useState, KeyboardEvent } from 'react';
import styles from './ConfigSampler.module.css';

/**
 * Valid tab identifiers for the configuration sampler.
 */
export type ConfigTabId = 'minimal' | 'full' | 'monorepo';

/**
 * Interface representing a row in the Key Knobs reference table.
 */
export interface KnobRow {
  /** The configuration key path */
  key: string;
  /** The default value for the key */
  defaultValue: string;
  /** Description of what this configuration key controls */
  controls: string;
}

/**
 * Verbatim list of important configuration keys, defaults, and descriptions.
 */
export const KNOBS: ReadonlyArray<KnobRow> = [
  {
    key: 'model.default',
    defaultValue: 'claude-sonnet-4-6',
    controls: 'Model for standard reviews',
  },
  {
    key: 'review.severity_threshold',
    defaultValue: 'info',
    controls: 'Minimum severity shown in output',
  },
  {
    key: 'review.tone',
    defaultValue: 'balanced',
    controls: 'balanced / concise / detailed',
  },
  {
    key: 'review.budget_cap_usd',
    defaultValue: 'null',
    controls: 'Max USD per review; null = no cap',
  },
  {
    key: 'features.inline_comments',
    defaultValue: 'false',
    controls: 'Post findings as inline diff comments',
  },
  {
    key: 'features.triage_pass',
    defaultValue: 'false',
    controls: 'Pre-classify PRs to route trivial ones cheaper',
  },
  {
    key: 'features.commands',
    defaultValue: 'false',
    controls: 'Enable @lychee command handling',
  },
  {
    key: 'conventions_file',
    defaultValue: 'null',
    controls: 'Path to a conventions file appended to the prompt',
  },
];

/**
 * Properties for the ConfigSamplerClient component.
 */
export interface ConfigSamplerClientProps {
  /** The initially active tab ID */
  defaultTab?: ConfigTabId;
  /** Pre-rendered Server Component panel for minimal configuration */
  minimalPanel: React.ReactNode;
  /** Pre-rendered Server Component panel for full configuration */
  fullPanel: React.ReactNode;
  /** Pre-rendered Server Component panel for monorepo configuration */
  monorepoPanel: React.ReactNode;
}

/**
 * Client component that manages the interactive tab switching, keyboard accessibility,
 * and key knobs reference table for the configuration sampler.
 *
 * @param props - Props containing active tab settings and pre-rendered panels.
 * @returns The client component markup with tab buttons, code panels, and reference table.
 */
export default function ConfigSamplerClient({
  defaultTab = 'minimal',
  minimalPanel,
  fullPanel,
  monorepoPanel,
}: ConfigSamplerClientProps): JSX.Element {
  const [activeTab, setActiveTab] = useState<ConfigTabId>(defaultTab);

  /**
   * Keyboard handler for roving tabindex and accessible keyboard navigation in tablist.
   *
   * @param e - The KeyboardEvent triggered by the tablist element.
   */
  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const tabs: ReadonlyArray<ConfigTabId> = ['minimal', 'full', 'monorepo'];
    const currentIndex = tabs.indexOf(activeTab);

    let newIndex = currentIndex;
    if (e.key === 'ArrowRight') {
      newIndex = (currentIndex + 1) % tabs.length;
    } else if (e.key === 'ArrowLeft') {
      newIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    } else if (e.key === 'Home') {
      newIndex = 0;
    } else if (e.key === 'End') {
      newIndex = tabs.length - 1;
    }

    if (newIndex !== currentIndex) {
      e.preventDefault();
      setActiveTab(tabs[newIndex]);
      const newTabButton = document.getElementById(`tab-${tabs[newIndex]}`);
      newTabButton?.focus();
    }
  };

  return (
    <section id="configure" className={styles.section}>
      <div className={styles.container}>
        <h2 className={styles.heading}>Configuration</h2>

        <div
          role="tablist"
          aria-label="Configuration sampler"
          className={styles.tablist}
          onKeyDown={handleKeyDown}
        >
          <button
            role="tab"
            aria-selected={activeTab === 'minimal'}
            aria-controls="panel-minimal"
            id="tab-minimal"
            tabIndex={activeTab === 'minimal' ? 0 : -1}
            onClick={() => setActiveTab('minimal')}
            className={`${styles.tab} ${activeTab === 'minimal' ? styles.activeTab : ''}`}
          >
            Minimal
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'full'}
            aria-controls="panel-full"
            id="tab-full"
            tabIndex={activeTab === 'full' ? 0 : -1}
            onClick={() => setActiveTab('full')}
            className={`${styles.tab} ${activeTab === 'full' ? styles.activeTab : ''}`}
          >
            Full-featured
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'monorepo'}
            aria-controls="panel-monorepo"
            id="tab-monorepo"
            tabIndex={activeTab === 'monorepo' ? 0 : -1}
            onClick={() => setActiveTab('monorepo')}
            className={`${styles.tab} ${activeTab === 'monorepo' ? styles.activeTab : ''}`}
          >
            Monorepo with scope rules
          </button>
        </div>

        <div className={styles.panelsContainer}>
          <div
            role="tabpanel"
            id="panel-minimal"
            aria-labelledby="tab-minimal"
            hidden={activeTab !== 'minimal'}
            className={`${styles.panel} ${activeTab === 'minimal' ? styles.activePanel : ''}`}
          >
            {minimalPanel}
          </div>
          <div
            role="tabpanel"
            id="panel-full"
            aria-labelledby="tab-full"
            hidden={activeTab !== 'full'}
            className={`${styles.panel} ${activeTab === 'full' ? styles.activePanel : ''}`}
          >
            {fullPanel}
          </div>
          <div
            role="tabpanel"
            id="panel-monorepo"
            aria-labelledby="tab-monorepo"
            hidden={activeTab !== 'monorepo'}
            className={`${styles.panel} ${activeTab === 'monorepo' ? styles.activePanel : ''}`}
          >
            {monorepoPanel}
          </div>
        </div>

        <h3 className={styles.tableSectionTitle}>Key Knobs</h3>
        <div className={styles.tableWrapper}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Key</th>
                <th scope="col">Default</th>
                <th scope="col">What it controls</th>
              </tr>
            </thead>
            <tbody>
              {KNOBS.map((knob) => (
                <tr key={knob.key}>
                  <td className={styles.monoCell}>
                    <code>{knob.key}</code>
                  </td>
                  <td className={styles.monoCell}>
                    <code>{knob.defaultValue}</code>
                  </td>
                  <td>{knob.controls}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className={styles.ctaWrapper}>
          <a href="/docs/configuration" className={styles.cta}>
            Full configuration reference →
          </a>
        </div>
      </div>
    </section>
  );
}
