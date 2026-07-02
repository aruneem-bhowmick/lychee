/** A group of doc slugs shown together under one section heading on the index. */
export interface DocsIndexGroup {
  /** Group heading text, matching the README Documentation Guide section name. */
  section: string;
  /** Member doc slugs, in the order they should be listed. */
  slugs: string[];
}

/**
 * The four canonical documentation groups, in reading order. Together their
 * slugs cover every known doc exactly once.
 */
export const DOCS_INDEX_GROUPS: ReadonlyArray<DocsIndexGroup> = [
  {
    section: 'Getting Started & Configuration',
    slugs: ['getting-started', 'configuration', 'commands'],
  },
  {
    section: 'Architecture & Design',
    slugs: ['architecture', 'glossary'],
  },
  {
    section: 'Operations, Deployment & Security',
    slugs: ['deployment', 'security', 'canary-setup', 'api-reference'],
  },
  {
    section: 'Development & Project Trajectory',
    slugs: ['development', 'roadmap'],
  },
];

/** Display titles for each doc slug, matching the sidebar labels. */
export const DOC_LABELS: Readonly<Record<string, string>> = {
  'getting-started': 'Getting Started',
  configuration: 'Configuration',
  commands: 'Commands',
  architecture: 'Architecture',
  glossary: 'Glossary',
  deployment: 'Deployment',
  security: 'Security',
  'canary-setup': 'Canary Setup',
  'api-reference': 'API Reference',
  development: 'Development',
  roadmap: 'Roadmap',
};
