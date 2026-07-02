import { describe, expect, it } from 'vitest';
import { fromMarkdown } from 'mdast-util-from-markdown';
import { toHtml } from 'hast-util-to-html';
import { toHast } from 'mdast-util-to-hast';
import type { Root, Table } from 'mdast';
import { remarkGfmTables } from './remark-gfm-tables';

/**
 * Parses markdown, runs the plugin, and converts the result to HTML so
 * assertions can check the actual rendered markup rather than the mdast
 * tree shape.
 *
 * @param markdown - The raw markdown source to render.
 * @returns The rendered HTML string.
 */
function renderToHtml(markdown: string): string {
  const tree = fromMarkdown(markdown) as Root;
  remarkGfmTables()(tree, { toString: () => markdown } as any);
  const hast = toHast(tree);
  return hast ? toHtml(hast) : '';
}

describe('remark-gfm-tables lib', () => {
  /**
   * Unit tests for table detection and cell-splitting on a raw mdast tree.
   */
  describe('Unit: table node construction', () => {
    it('replaces a table-shaped paragraph with a table node', () => {
      const tree = fromMarkdown('| A | B |\n|---|---|\n| 1 | 2 |\n') as Root;
      remarkGfmTables()(tree, { toString: () => '| A | B |\n|---|---|\n| 1 | 2 |\n' } as any);

      expect(tree.children).toHaveLength(1);
      expect(tree.children[0].type).toBe('table');
    });

    it('leaves ordinary paragraphs untouched', () => {
      const markdown = 'Just a normal paragraph.\nWith a second line.\n';
      const tree = fromMarkdown(markdown) as Root;
      remarkGfmTables()(tree, { toString: () => markdown } as any);

      expect(tree.children[0].type).toBe('paragraph');
    });

    it('does not split a pipe inside a code span', () => {
      const markdown = '| Key | Type |\n|-----|------|\n| `x` | `float\\|null` |\n';
      const tree = fromMarkdown(markdown) as Root;
      remarkGfmTables()(tree, { toString: () => markdown } as any);

      const table = tree.children[0] as Table;
      const bodyRow = table.children[1];
      expect(bodyRow.children).toHaveLength(2);
    });

    it('derives column alignment from the delimiter row', () => {
      const markdown = '| L | C | R |\n|:--|:-:|--:|\n| 1 | 2 | 3 |\n';
      const tree = fromMarkdown(markdown) as Root;
      remarkGfmTables()(tree, { toString: () => markdown } as any);

      const table = tree.children[0] as Table;
      expect(table.align).toEqual(['left', 'center', 'right']);
    });
  });

  /**
   * Component-level: full markdown -> HTML rendering through mdast-util-to-hast.
   */
  describe('Component: HTML rendering', () => {
    it('renders a thead/tbody table with the correct cell text', () => {
      const html = renderToHtml('| Name | Value |\n|------|-------|\n| Alpha | 1 |\n| Beta | 2 |\n');

      expect(html).toContain('<table>');
      expect(html).toContain('<thead>');
      expect(html).toContain('<tbody>');
      expect(html).toContain('<th>Name</th>');
      expect(html).toContain('<td>Alpha</td>');
      expect(html).toContain('<td>2</td>');
    });

    it('parses inline formatting inside cells', () => {
      const html = renderToHtml(
        '| Key | Description |\n|-----|-------------|\n| `scope_rules` | See [rules](CONFIGURATION.md) |\n'
      );

      expect(html).toContain('<code>scope_rules</code>');
      expect(html).toContain('<a href="CONFIGURATION.md">rules</a>');
    });
  });

  /**
   * Sanity: a paragraph merely resembling a table (no valid delimiter row)
   * is never converted.
   */
  describe('Sanity: false-positive guards', () => {
    it('requires the second line to be a valid delimiter row', () => {
      const markdown = '| Not a table |\nJust more prose text.\n';
      const tree = fromMarkdown(markdown) as Root;
      remarkGfmTables()(tree, { toString: () => markdown } as any);

      expect(tree.children[0].type).toBe('paragraph');
    });

    it('requires at least a header and delimiter line', () => {
      const markdown = '| Only one line |\n';
      const tree = fromMarkdown(markdown) as Root;
      remarkGfmTables()(tree, { toString: () => markdown } as any);

      expect(tree.children[0].type).toBe('paragraph');
    });
  });

  /**
   * Regression fixture matching the real docs corpus's table shape,
   * including a trailing prose paragraph that must stay untouched.
   */
  describe('Regression: mixed table + prose fixture', () => {
    it('converts only the table block, leaving surrounding prose intact', () => {
      const markdown = [
        '# Title',
        '',
        '| Key | Type | Default |',
        '|-----|------|---------|',
        '| `tone` | `str` | `balanced` |',
        '',
        'Prose after the table stays a paragraph.',
        '',
      ].join('\n');

      const tree = fromMarkdown(markdown) as Root;
      remarkGfmTables()(tree, { toString: () => markdown } as any);

      expect(tree.children.map((child) => child.type)).toEqual([
        'heading',
        'table',
        'paragraph',
      ]);
    });
  });

  /**
   * Smoke test: importing the module and running it on an empty document
   * does not throw.
   */
  describe('Smoke', () => {
    it('handles an empty document without throwing', () => {
      const tree = fromMarkdown('') as Root;
      expect(() => remarkGfmTables()(tree, { toString: () => '' } as any)).not.toThrow();
    });
  });
});
