import '@testing-library/jest-dom';
import { expect, vi } from 'vitest';
import * as matchers from '@testing-library/jest-dom/matchers';
import { toHaveNoViolations } from 'jest-axe';

expect.extend(matchers);
expect.extend(toHaveNoViolations);

// jsdom doesn't implement scrollIntoView; components that smooth-scroll to
// in-page anchors (e.g. NavBar) call it defensively, but tests still need
// a stand-in so those calls don't throw.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}
