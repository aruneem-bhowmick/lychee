import { describe, expect, it } from 'vitest';
import { rehypeRewriteDocLinks, rewriteHref } from './link-rewriter';
import { SLUG_TO_FILE } from './docs';

describe('link-rewriter lib', () => {
  /**
   * Exhaustive rewriteHref() cases from the docs link-rewriting rule.
   */
  describe('Unit: rewriteHref', () => {
    it('rewrites a bare filename to its site route', () => {
      expect(rewriteHref('CONFIGURATION.md')).toBe('/docs/configuration');
    });

    it('preserves a fragment anchor', () => {
      expect(rewriteHref('CONFIGURATION.md#scope-rules')).toBe(
        '/docs/configuration#scope-rules'
      );
    });

    it('rewrites a relative ./ prefixed link', () => {
      expect(rewriteHref('./GETTING-STARTED.md')).toBe('/docs/getting-started');
    });

    it('rewrites a hyphenated filename', () => {
      expect(rewriteHref('API-REFERENCE.md')).toBe('/docs/api-reference');
    });

    it('leaves a same-page fragment unchanged', () => {
      expect(rewriteHref('#local-anchor')).toBe('#local-anchor');
    });

    it('leaves an external link unchanged', () => {
      expect(rewriteHref('https://github.com/x')).toBe('https://github.com/x');
    });

    it('leaves an already-rewritten site route unchanged', () => {
      expect(rewriteHref('/docs/security')).toBe('/docs/security');
    });

    it('leaves an unknown markdown target unchanged', () => {
      expect(rewriteHref('FOO.md')).toBe('FOO.md');
    });

    it('is case-insensitive on the filename', () => {
      expect(rewriteHref('configuration.md')).toBe('/docs/configuration');
    });

    it('rewrites a docs/-prefixed relative path', () => {
      expect(rewriteHref('docs/CONFIGURATION.md')).toBe('/docs/configuration');
    });

    it('leaves an empty href unchanged', () => {
      expect(rewriteHref('')).toBe('');
    });

    it('leaves a mailto link unchanged', () => {
      expect(rewriteHref('mailto:hello@example.com')).toBe('mailto:hello@example.com');
    });
  });

  /**
   * The rehype plugin wiring rewriteHref into an actual hast tree.
   */
  describe('Component: rehypeRewriteDocLinks', () => {
    it('rewrites hrefs on anchor elements in place', () => {
      const tree = {
        type: 'root',
        children: [
          {
            type: 'element',
            tagName: 'a',
            properties: { href: 'CONFIGURATION.md#scope-rules' },
            children: [],
          },
          {
            type: 'element',
            tagName: 'a',
            properties: { href: 'https://github.com/x' },
            children: [],
          },
        ],
      } as any;

      rehypeRewriteDocLinks()(tree);

      expect(tree.children[0].properties.href).toBe('/docs/configuration#scope-rules');
      expect(tree.children[1].properties.href).toBe('https://github.com/x');
    });

    it('ignores non-anchor elements and anchors without an href', () => {
      const tree = {
        type: 'root',
        children: [
          { type: 'element', tagName: 'p', properties: {}, children: [] },
          { type: 'element', tagName: 'a', properties: {}, children: [] },
        ],
      } as any;

      expect(() => rehypeRewriteDocLinks()(tree)).not.toThrow();
      expect(tree.children[1].properties.href).toBeUndefined();
    });
  });

  /**
   * Regression: the reverse filename -> slug map, derived from the public
   * SLUG_TO_FILE + rewriteHref API, stays stable.
   */
  describe('Regression: reverse filename map', () => {
    it('matches the snapshot of every known filename rewritten to its slug route', () => {
      const reverseMap = Object.fromEntries(
        Object.values(SLUG_TO_FILE).map((file) => [file, rewriteHref(file.split('/').pop()!)])
      );

      expect(reverseMap).toMatchSnapshot();
    });
  });

  /**
   * Smoke test: importing the module does not throw and exports are usable.
   */
  describe('Smoke', () => {
    it('imports without throwing', () => {
      expect(typeof rewriteHref).toBe('function');
      expect(typeof rehypeRewriteDocLinks).toBe('function');
    });
  });
});
