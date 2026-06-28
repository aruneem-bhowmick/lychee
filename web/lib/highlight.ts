import { codeToHtml } from 'shiki';

export interface HighlightOptions {
  code: string;
  lang: string;
}

/**
 * Returns highlighted HTML string (a <pre><code>...</code></pre> fragment).
 * Uses shiki with 'github-dark' theme.
 * Fallbacks to 'text' if the language is unknown.
 *
 * @param opts - Options including the raw code and the language identifier.
 * @returns A promise resolving to the HTML string.
 */
export async function highlightCode(opts: HighlightOptions): Promise<string> {
  const supportedLangs = ['yaml', 'bash', 'text', 'tsx', 'ts', 'json', 'python'];
  const lang = supportedLangs.includes(opts.lang) ? opts.lang : 'text';
  
  try {
    return await codeToHtml(opts.code, {
      lang,
      theme: 'github-dark',
    });
  } catch (error) {
    // Fallback if shiki fails for any reason
    return await codeToHtml(opts.code, {
      lang: 'text',
      theme: 'github-dark',
    });
  }
}
