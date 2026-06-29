'use client';

import React, { useState, KeyboardEvent } from 'react';
import styles from './SetupTabs.module.css';

export type SetupTabId = 'github-actions' | 'github-app';

export interface SetupTabsClientProps {
  defaultTab?: SetupTabId;
  actionsPanel: React.ReactNode;
  appPanel: React.ReactNode;
}

export default function SetupTabsClient({
  defaultTab = 'github-actions',
  actionsPanel,
  appPanel,
}: SetupTabsClientProps) {
  const [activeTab, setActiveTab] = useState<SetupTabId>(defaultTab);

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const tabs = ['github-actions', 'github-app'] as const;
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
    <section id="setup" className={styles.section}>
      <div className={styles.container}>
        <h2>Setup</h2>
        <div
          role="tablist"
          aria-label="Setup mode"
          className={styles.tablist}
          onKeyDown={handleKeyDown}
        >
          <button
            role="tab"
            aria-selected={activeTab === 'github-actions'}
            aria-controls="panel-github-actions"
            id="tab-github-actions"
            tabIndex={activeTab === 'github-actions' ? 0 : -1}
            onClick={() => setActiveTab('github-actions')}
            className={`${styles.tab} ${activeTab === 'github-actions' ? styles.activeTab : ''}`}
          >
            GitHub Actions
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'github-app'}
            aria-controls="panel-github-app"
            id="tab-github-app"
            tabIndex={activeTab === 'github-app' ? 0 : -1}
            onClick={() => setActiveTab('github-app')}
            className={`${styles.tab} ${activeTab === 'github-app' ? styles.activeTab : ''}`}
          >
            GitHub App
          </button>
        </div>

        <div className={styles.panelsContainer}>
          <div
            role="tabpanel"
            id="panel-github-actions"
            aria-labelledby="tab-github-actions"
            hidden={activeTab !== 'github-actions'}
            className={`${styles.panel} ${activeTab === 'github-actions' ? styles.activePanel : ''}`}
          >
            {actionsPanel}
          </div>
          <div
            role="tabpanel"
            id="panel-github-app"
            aria-labelledby="tab-github-app"
            hidden={activeTab !== 'github-app'}
            className={`${styles.panel} ${activeTab === 'github-app' ? styles.activePanel : ''}`}
          >
            {appPanel}
          </div>
        </div>
      </div>
    </section>
  );
}
