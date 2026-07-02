import { describe, it, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

describe('animations.css motion system', () => {
  const cssPath = path.join(__dirname, 'animations.css');
  const cssContent = fs.readFileSync(cssPath, 'utf8');

  it('smoke: file exists and is non-empty', () => {
    expect(cssContent.length).toBeGreaterThan(0);
  });

  it('unit: defines the fade-up keyframes used for section entry and pipeline stagger', () => {
    expect(cssContent).toMatch(/@keyframes\s+fade-up\s*\{/);
    expect(cssContent).toMatch(/from\s*\{\s*opacity:\s*0;\s*transform:\s*translateY\(16px\);\s*\}/);
    expect(cssContent).toMatch(/to\s*\{\s*opacity:\s*1;\s*transform:\s*none;\s*\}/);
  });

  it('unit: defines the badge-pulse keyframes', () => {
    expect(cssContent).toMatch(/@keyframes\s+badge-pulse\s*\{/);
    expect(cssContent).toMatch(/transform:\s*scale\(1\.06\)/);
  });

  it('sanity: the badge-pulse utility class is one-shot, not repeating', () => {
    const badgePulseRule = cssContent.match(/\.badge-pulse\s*\{[^}]*\}/)?.[0] ?? '';
    expect(badgePulseRule).toMatch(/animation-iteration-count:\s*1;/);
    expect(badgePulseRule).not.toMatch(/animation-iteration-count:\s*infinite/);
  });

  it('accessibility: gates the badge pulse behind an explicit prefers-reduced-motion override', () => {
    expect(cssContent).toMatch(/@media\s*\(\s*prefers-reduced-motion:\s*reduce\s*\)\s*\{/);
    const reducedMotionBlock = cssContent.slice(cssContent.indexOf('@media (prefers-reduced-motion: reduce)'));
    expect(reducedMotionBlock).toMatch(/\.badge-pulse\s*\{\s*animation:\s*none;\s*\}/);
  });

  it('regression: snapshot the raw file contents', () => {
    expect(cssContent).toMatchSnapshot();
  });
});
