import { readFileSync } from 'node:fs';
import { join, basename } from 'node:path';
import matter from 'gray-matter';
import { notFound } from 'next/navigation';

/** A single rendered documentation page, resolved from its markdown source. */
export interface DocPage {
  /** Route slug, e.g. "configuration". */
  slug: string;
  /** Frontmatter title, else the first H1 in the body, else a humanized slug. */
  title: string;
  /** Frontmatter description, else the first sentence of the first paragraph. */
  description: string;
  /** Raw markdown body with frontmatter stripped. */
  content: string;
}

/** The canonical slug -> source filename mapping (single source of truth). */
export const SLUG_TO_FILE: Readonly<Record<string, string>> = {
  'getting-started': 'docs/GETTING-STARTED.md',
  configuration: 'docs/CONFIGURATION.md',
  commands: 'docs/COMMANDS.md',
  architecture: 'docs/ARCHITECTURE.md',
  glossary: 'docs/GLOSSARY.md',
  deployment: 'docs/DEPLOYMENT.md',
  security: 'docs/SECURITY.md',
  'canary-setup': 'docs/CANARY-SETUP.md',
  'api-reference': 'docs/API-REFERENCE.md',
  development: 'docs/DEVELOPMENT.md',
  roadmap: 'docs/ROADMAP.md',
};

/** Ordered slugs used by the sidebar and index. */
export const DOC_SLUGS: ReadonlyArray<string> = Object.keys(SLUG_TO_FILE);

/** Absolute path to the sibling `docs/` directory, resolved at build time. */
const DOCS_DIR = join(process.cwd(), '..', 'docs');

/**
 * Turns a slug like "getting-started" into a humanized title like
 * "Getting Started". Used only when a doc has neither frontmatter nor an H1.
 *
 * @param slug - The route slug to humanize.
 * @returns The humanized title.
 */
function humanizeSlug(slug: string): string {
  return slug
    .split('-')
    .filter(Boolean)
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * Derives a doc's title from its first H1 heading, falling back to a
 * humanized slug when no heading is present.
 *
 * @param content - The frontmatter-stripped markdown body.
 * @param slug - The route slug, used as a last-resort fallback.
 * @returns The derived title.
 */
function deriveTitle(content: string, slug: string): string {
  const heading = content.match(/^#\s+(.+)$/m);
  return heading ? heading[1].trim() : humanizeSlug(slug);
}

/**
 * Derives a doc's description from the first sentence of its first
 * non-heading paragraph.
 *
 * @param content - The frontmatter-stripped markdown body.
 * @returns The derived description, or an empty string if none is found.
 */
function deriveDescription(content: string): string {
  const blocks = content
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean);
  const paragraph = blocks.find(
    (block) => !block.startsWith('#') && !block.startsWith('|') && !block.startsWith('```')
  );
  if (!paragraph) return '';

  const flattened = paragraph.replace(/\s+/g, ' ').trim();
  const sentence = flattened.match(/^.*?[.!?](?=\s|$)/);
  return sentence ? sentence[0] : flattened;
}

/**
 * Returns every known documentation slug, in canonical sidebar order.
 *
 * @returns The list of doc slugs.
 */
export function getAllDocSlugs(): string[] {
  return [...DOC_SLUGS];
}

/**
 * Reads, parses, and resolves a single documentation page by its route slug.
 * Frontmatter (if any) takes precedence over values derived from the body.
 *
 * @param slug - The route slug to resolve, e.g. "configuration".
 * @returns The resolved doc page.
 * @throws Calls Next.js's `notFound()` (which throws) when the slug is unknown.
 */
export function getDocBySlug(slug: string): DocPage {
  const relativeFile = SLUG_TO_FILE[slug];
  if (!relativeFile) {
    notFound();
  }

  const filePath = join(DOCS_DIR, basename(relativeFile));
  const raw = readFileSync(filePath, 'utf8');
  const { data, content } = matter(raw);
  const body = content.replace(/^\n+/, '');

  const title = typeof data.title === 'string' ? data.title : deriveTitle(body, slug);
  const description =
    typeof data.description === 'string' ? data.description : deriveDescription(body);

  return { slug, title, description, content: body };
}
