import { describe, it, expect } from 'vitest';
import { highlightCode } from './highlight';

/**
 * Strips HTML tags from a shiki output fragment to recover the visible
 * text, since shiki wraps each syntax-highlighted token in its own
 * `<span>`, splitting literal substrings like `"a: 1"` across elements.
 *
 * @param html - The HTML fragment produced by `highlightCode`.
 * @returns The concatenated visible text content, tags removed.
 */
function visibleText(html: string): string {
  return html.replace(/<[^>]+>/g, '');
}

describe('highlightCode', () => {
  it('highlights known language correctly', async () => {
    const html = await highlightCode({ code: 'a: 1', lang: 'yaml' });
    expect(html).toContain('<pre');
    expect(html).toContain('<code');
    expect(visibleText(html)).toContain('a: 1');
  });

  it('falls back to text for unknown languages without throwing', async () => {
    const html = await highlightCode({ code: 'a: 1', lang: 'klingon' });
    expect(html).toContain('<pre');
    expect(html).toContain('<code');
    expect(visibleText(html)).toContain('a: 1');
  });
});
