import { visit } from 'unist-util-visit';
import { toString } from 'hast-util-to-string';
import rehypePrettyCode, { type Options as PrettyCodeOptions } from 'rehype-pretty-code';
import type { Element, Root } from 'hast';
import type { PluggableList } from 'unified';
import { rehypeRewriteDocLinks } from './link-rewriter';

const HEADING_TAGS = new Set(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']);

/**
 * Converts heading text into a URL-safe slug: lowercased, punctuation
 * stripped, whitespace collapsed to single hyphens.
 *
 * @param text - The heading's plain-text content.
 * @returns The slugified id, or an empty string if nothing survives.
 */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/**
 * Minimal, dependency-free stand-in for `rehype-slug`: assigns a unique
 * `id` to every heading element that doesn't already have one, so headings
 * are addressable via URL fragments. Duplicate slugs within a single
 * document are disambiguated with a numeric suffix.
 *
 * @returns A transformer that mutates heading elements in place.
 */
function rehypeHeadingSlugs() {
  return (tree: Root) => {
    const seen = new Map<string, number>();

    visit(tree, 'element', (node: Element) => {
      if (!HEADING_TAGS.has(node.tagName)) return;
      if (node.properties?.id) return;

      const base = slugify(toString(node)) || 'section';
      const count = seen.get(base) ?? 0;
      seen.set(base, count + 1);

      node.properties = {
        ...node.properties,
        id: count === 0 ? base : `${base}-${count}`,
      };
    });
  };
}

const PRETTY_CODE_OPTIONS: PrettyCodeOptions = {
  theme: 'github-dark',
  keepBackground: true,
};

/**
 * Assembles the ordered rehype plugin pipeline used to render compiled docs
 * markdown: heading slugs for anchor links, Shiki-powered syntax
 * highlighting of fenced code blocks, and rewriting of internal doc links.
 *
 * @returns The ordered list of rehype plugins for `compileMDX`.
 */
export function getRehypePlugins(): PluggableList {
  return [rehypeHeadingSlugs, [rehypePrettyCode, PRETTY_CODE_OPTIONS], rehypeRewriteDocLinks];
}
