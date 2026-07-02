import fs from 'fs';
import path from 'path';
import { render, screen } from '@testing-library/react';
import { axe } from 'jest-axe';
import React from 'react';
import { vi } from 'vitest';

vi.mock('next/font/google', () => ({
  Inter: () => ({ variable: '--font-inter' }),
  JetBrains_Mono: () => ({ variable: '--font-jetbrains-mono' }),
}));

// `Home` composes several async Server Components (via `CodeBlock`) that
// RTL's synchronous `render` cannot resolve; mock it the same way
// `app/page.test.tsx` does so this file's own Home-rendering checks work.
vi.mock('@/components/CodeBlock', () => ({
  default: () => <div data-testid="code-block-mock">CodeBlock Mock</div>,
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

import Home from '../app/page';
import RootLayout from '../app/layout';

/**
 * Test suite to validate that configuration invariants hold.
 * It verifies `package.json`, `tsconfig.json`, `vercel.json`, and `.gitignore`.
 */
describe('Scaffold Configuration invariants', () => {
  it('validates package.json invariants', () => {
    const pkgPath = path.resolve(__dirname, '../package.json');
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));

    expect(pkg.scripts.build).toBe('next build');
    expect(pkg.scripts.test).toBe('vitest run');
    expect(pkg.dependencies.next).toBeDefined();
    expect(pkg.dependencies.shiki).toBeDefined();
    expect(pkg.dependencies['rehype-pretty-code']).toBeDefined();
  });

  it('validates tsconfig.json invariants', () => {
    const tsconfigPath = path.resolve(__dirname, '../tsconfig.json');
    const tsconfigRaw = fs.readFileSync(tsconfigPath, 'utf8');
    const tsconfig = JSON.parse(tsconfigRaw);

    expect(tsconfig.compilerOptions.strict).toBe(true);
    expect(tsconfig.compilerOptions.paths['@/*']).toBeDefined();
  });

  it('validates vercel.json invariants', () => {
    const vercelPath = path.resolve(__dirname, '../vercel.json');
    const vercel = JSON.parse(fs.readFileSync(vercelPath, 'utf8'));

    expect(vercel.framework).toBe('nextjs');
  });

  it('validates .gitignore invariants', () => {
    const gitignorePath = path.resolve(__dirname, '../.gitignore');
    const gitignore = fs.readFileSync(gitignorePath, 'utf8');

    expect(gitignore).toContain('.next');
  });
});

/**
 * Component testing suite for basic layout and structural requirements.
 */
describe('Component Rendering and Accessibility', () => {
  it('renders the Home component correctly', () => {
    render(<Home />);
    expect(screen.getByText(/Peel back your pull requests\./i)).toBeInTheDocument();
  });

  it('matches the Home component snapshot', () => {
    const { container } = render(<Home />);
    expect(container).toMatchSnapshot();
  });

  it('Home component has no accessibility violations', async () => {
    const { container } = render(<Home />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  }, 20000);
});

/**
 * Basic smoke tests to ensure essential module components exist and are callable.
 */
describe('Smoke tests', () => {
  it('Layout and Page are functions', () => {
    expect(typeof RootLayout).toBe('function');
    expect(typeof Home).toBe('function');
  });
});
