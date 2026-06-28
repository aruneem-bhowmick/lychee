import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CodeBlock from './CodeBlock';
import { axe } from 'jest-axe';
import React from 'react';

// Wrap async Server Component to test it synchronously
async function renderAsync(element: JSX.Element) {
  // @ts-expect-error - RSC can be awaited in tests
  const resolved = await element.type(element.props);
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
    await renderAsync(
      <CodeBlock code="pip install -e ." lang="bash" filename=".lychee.yml" />
    );

    expect(screen.getByText('.lychee.yml')).toBeInTheDocument();
    expect(screen.getByText('bash')).toBeInTheDocument();
    expect(screen.getByText(/pip install -e ./)).toBeInTheDocument();

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
    await renderAsync(<CodeBlock code={codeWithSpaces} lang="text" />);
    // Testing library's getByText ignores spacing in queries, 
    // so we verify using text content directly
    const codeElement = screen.getByText((_, element) => {
      return element?.textContent?.includes('  line 1') ?? false;
    });
    expect(codeElement).toBeInTheDocument();
  });
});
