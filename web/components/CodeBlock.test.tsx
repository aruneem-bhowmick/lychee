import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CodeBlock from './CodeBlock';
import { axe } from 'jest-axe';
import React from 'react';

/**
 * Resolves an async Server Component's element by invoking its function
 * type directly with its props, then renders the resulting JSX. RTL's
 * `render` only accepts already-resolved elements, so this is how async
 * Server Components (like `CodeBlock`) get exercised in tests.
 *
 * @param element - The unresolved async Server Component element.
 * @returns The RTL render result for the resolved element.
 */
async function renderAsync(element: JSX.Element) {
  const resolved = await (element.type as unknown as (props: unknown) => Promise<JSX.Element>)(element.props);
  return render(resolved);
}

// Mock clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: vi.fn().mockResolvedValue(undefined),
  },
});

describe('CodeBlock', () => {
  it('renders filename, lang tag, and code', async () => {
    const { container } = await renderAsync(
      <CodeBlock code="pip install -e ." lang="bash" filename=".lychee.yml" />
    );

    expect(screen.getByText('.lychee.yml')).toBeInTheDocument();
    expect(screen.getByText('bash')).toBeInTheDocument();
    // shiki splits the code into one <span> per token, so no single
    // element's direct text matches the full phrase; check the rendered
    // text as a whole instead of relying on RTL's default text matcher.
    expect(container.textContent).toContain('pip install -e .');

    const copyBtn = screen.getByRole('button', { name: 'Copy code to clipboard' });
    expect(copyBtn).toBeInTheDocument();
  });

  it('renders lang tag using label override', async () => {
    await renderAsync(
      <CodeBlock code="echo 'test'" lang="bash" label="shell" />
    );
    expect(screen.getByText('shell')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = await renderAsync(
      <CodeBlock code="test" lang="text" />
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('preserves whitespace and formatting for code', async () => {
    const codeWithSpaces = `  line 1\n    line 2`;
    const { container } = await renderAsync(<CodeBlock code={codeWithSpaces} lang="text" />);
    // Testing library's getByText ignores spacing in queries, and shiki
    // wraps every token in its own element (so several ancestors share
    // the same textContent) — checking the rendered text directly avoids
    // both pitfalls.
    expect(container.textContent).toContain('  line 1');
    expect(container.textContent).toContain('    line 2');
  });
});
