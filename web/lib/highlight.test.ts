import { describe, it, expect } from 'vitest';
import { highlightCode } from './highlight';

describe('highlightCode', () => {
  it('highlights known language correctly', async () => {
    const html = await highlightCode({ code: 'a: 1', lang: 'yaml' });
    expect(html).toContain('<pre');
    expect(html).toContain('<code');
    expect(html).toContain('a: 1');
  });

  it('falls back to text for unknown languages without throwing', async () => {
    const html = await highlightCode({ code: 'a: 1', lang: 'klingon' });
    expect(html).toContain('<pre');
    expect(html).toContain('<code');
    expect(html).toContain('a: 1');
  });
});
