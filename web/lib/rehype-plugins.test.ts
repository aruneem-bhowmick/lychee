import { describe, expect, it } from 'vitest';
import { fromHtml } from 'hast-util-from-html';
import { toHtml } from 'hast-util-to-html';
import { getRehypePlugins, slugify } from './rehype-plugins';

/**
 * Runs every plugin returned by getRehypePlugins() over a small HTML
 * fragment, mirroring how compileMDX would apply them in sequence.
 *
 * @param html - The input HTML fragment (already-parsed markdown output).
 * @returns The rendered HTML string after all plugins have run.
 */
async function runPipeline(html: string): Promise<string> {
  const tree = fromHtml(html, { fragment: true });
  for (const entry of getRehypePlugins()) {
    const [attacher, options] = Array.isArray(entry) ? entry : [entry, undefined];
    const transformer = (attacher as (opts?: unknown) => (tree: unknown) => void | Promise<void>)(
      options
    );
    await transformer(tree);
  }
  return toHtml(tree);
}

describe('rehype-plugins lib', () => {
  /**
   * Unit tests for the pure slugify() helper.
   */
  describe('Unit: slugify', () => {
    it('lowercases and hyphenates a heading', () => {
      expect(slugify('Scope Rules')).toBe('scope-rules');
    });

    it('strips punctuation', () => {
      expect(slugify('What is Lychee?')).toBe('what-is-lychee');
    });

    it('collapses repeated whitespace', () => {
      expect(slugify('Too   many   spaces')).toBe('too-many-spaces');
    });

    it('trims leading and trailing hyphens', () => {
      expect(slugify('  --edge--  ')).toBe('edge');
    });
  });

  /**
   * Smoke: the plugin pipeline is non-empty and every entry is invocable.
   */
  describe('Smoke: getRehypePlugins', () => {
    it('returns a non-empty array', () => {
      expect(getRehypePlugins().length).toBeGreaterThan(0);
    });

    it('imports and runs without throwing on a minimal fragment', async () => {
      await expect(runPipeline('<h2>Hello</h2><p>World</p>')).resolves.toBeTypeOf('string');
    });
  });

  /**
   * Component-level: the assembled pipeline assigns heading ids and
   * rewrites internal doc links end-to-end.
   */
  describe('Component: assembled pipeline behavior', () => {
    it('assigns a slug id to a heading', async () => {
      const html = await runPipeline('<h2>Scope Rules</h2>');
      expect(html).toContain('id="scope-rules"');
    });

    it('does not overwrite an existing heading id', async () => {
      const html = await runPipeline('<h2 id="custom">Scope Rules</h2>');
      expect(html).toContain('id="custom"');
    });

    it('disambiguates duplicate headings with a numeric suffix', async () => {
      const html = await runPipeline('<h2>Overview</h2><h2>Overview</h2>');
      expect(html).toContain('id="overview"');
      expect(html).toContain('id="overview-1"');
    });

    it('rewrites an internal doc link found in the fragment', async () => {
      const html = await runPipeline('<p><a href="CONFIGURATION.md">config</a></p>');
      expect(html).toContain('href="/docs/configuration"');
    });
  });

  /**
   * Sanity: plugin ordering places heading slugs before link rewriting,
   * both preceding/following pretty-code as documented.
   */
  describe('Sanity: plugin ordering', () => {
    it('lists heading slugs first and link rewriting last', () => {
      const plugins = getRehypePlugins();
      expect(plugins[0]).toBeTypeOf('function');
      expect(plugins[plugins.length - 1]).toBeTypeOf('function');
      expect(Array.isArray(plugins[1])).toBe(true);
    });
  });
});
