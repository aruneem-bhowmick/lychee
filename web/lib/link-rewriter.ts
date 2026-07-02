import { visit } from 'unist-util-visit';
import type { Root, Element } from 'hast';
import { SLUG_TO_FILE } from './docs';

/** Case-insensitive filename -> slug reverse map, derived from `SLUG_TO_FILE`. */
const FILENAME_TO_SLUG: Readonly<Record<string, string>> = Object.fromEntries(
  Object.entries(SLUG_TO_FILE).map(([slug, file]) => {
    const filename = file.split('/').pop() ?? file;
    return [filename.toLowerCase(), slug];
  })
);

/**
 * Splits an href into its path and fragment (hash) parts.
 *
 * @param href - The raw href value.
 * @returns A tuple of `[path, fragment]`; `fragment` omits the leading `#`.
 */
function splitFragment(href: string): [string, string | undefined] {
  const hashIndex = href.indexOf('#');
  if (hashIndex === -1) return [href, undefined];
  return [href.slice(0, hashIndex), href.slice(hashIndex + 1)];
}

/**
 * Rewrites an `<a href>` value pointing at a docs markdown file to its site
 * route, preserving any fragment anchor. External links, same-page
 * fragments, already-rewritten routes, and unrecognized `.md` targets are
 * left unchanged.
 *
 * @param href - The raw href value found in rendered markdown.
 * @returns The rewritten href, or the original value when no rewrite applies.
 */
export function rewriteHref(href: string): string {
  if (!href) return href;
  if (href.startsWith('#')) return href;
  if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return href;
  if (href.startsWith('/')) return href;

  const [pathPart, fragment] = splitFragment(href);
  if (!pathPart.toLowerCase().endsWith('.md')) return href;

  const filename = pathPart.split('/').pop() ?? pathPart;
  const slug = FILENAME_TO_SLUG[filename.toLowerCase()];
  if (!slug) return href;

  return fragment ? `/docs/${slug}#${fragment}` : `/docs/${slug}`;
}

/**
 * Rehype plugin that rewrites every anchor's `href` pointing at a docs
 * markdown file to the corresponding site route.
 *
 * @returns A transformer visiting `a` elements and rewriting their `href`.
 */
export function rehypeRewriteDocLinks(): (tree: Root) => void {
  return (tree: Root) => {
    visit(tree, 'element', (node: Element) => {
      if (node.tagName !== 'a') return;
      const href = node.properties?.href;
      if (typeof href !== 'string') return;
      node.properties.href = rewriteHref(href);
    });
  };
}
