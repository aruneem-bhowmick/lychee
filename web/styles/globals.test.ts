import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

describe('globals.css design system', () => {
  const cssPath = path.join(__dirname, 'globals.css');
  const cssContent = fs.readFileSync(cssPath, 'utf8');

  it('smoke: file exists and is non-empty', () => {
    expect(cssContent.length).toBeGreaterThan(0);
    expect(cssContent).toContain(':root {');
    expect(cssContent).toContain('@media (min-width: 768px)');
  });

  it('unit: contains required custom properties', () => {
    const requiredTokens = [
      '--color-bg', '--color-surface', '--color-surface-raised', '--color-border',
      '--color-text', '--color-text-muted', '--color-accent-red', '--color-accent-pink',
      '--color-success', '--color-warning', '--color-danger', '--color-info',
      '--color-stem', '--color-near-white', '--gradient-primary',
      '--font-sans', '--font-mono', '--font-size-display', '--font-size-heading',
      '--font-size-card-title', '--font-size-body', '--font-size-code', '--font-size-nav',
      '--font-weight-display', '--font-weight-heading', '--font-weight-card-title',
      '--font-weight-nav', '--font-weight-body',
      '--space-unit', '--space-1', '--space-2', '--space-3', '--space-4',
      '--space-6', '--space-8', '--space-12',
      '--section-pad-desktop', '--section-pad-mobile',
      '--radius-card', '--radius-button', '--radius-code',
      '--content-max-width', '--nav-height',
      '--ease-standard', '--dur-fast', '--dur-base', '--dur-slow'
    ];

    requiredTokens.forEach(token => {
      const regex = new RegExp(`\\s${token}:\\s`);
      expect(cssContent).toMatch(regex);
    });
  });

  it('unit: assert exact hex values for specific colors', () => {
    expect(cssContent).toMatch(/--color-bg:\s*#0d1117;/);
    expect(cssContent).toMatch(/--color-accent-red:\s*#e03a3e;/);
    expect(cssContent).toMatch(/--color-accent-pink:\s*#e94b8a;/);
    expect(cssContent).toMatch(/--color-danger:\s*#da3633;/);
  });

  it('sanity: assert specific complex property values', () => {
    expect(cssContent).toMatch(/--gradient-primary:\s*linear-gradient\(90deg, #e03a3e 0%, #e94b8a 100%\);/);
    expect(cssContent).toMatch(/--font-size-display:\s*clamp\(2rem, 5vw, 4rem\);/);
  });

  it('accessibility: assert contrast pair is documented', () => {
    expect(cssContent).toMatch(/--color-text:\s*#e6edf3;/);
    expect(cssContent).toMatch(/--color-bg:\s*#0d1117;/);
  });

  it('responsive/mobile: assert overriding section padding for desktop', () => {
    const mediaQueryRegex = /@media\s*\(\s*min-width:\s*768px\s*\)\s*\{\s*\.section\s*\{\s*padding-block:\s*var\(--section-pad-desktop\);\s*\}\s*\}/;
    expect(cssContent).toMatch(mediaQueryRegex);
  });

  it('snapshot: lock the raw file contents string', () => {
    expect(cssContent).toMatchSnapshot();
  });
});
