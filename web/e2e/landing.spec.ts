import { expect, test } from '@playwright/test';

test.describe('Landing page', () => {
  test('loads with no console errors and the canonical document title', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto('/');

    await expect(page).toHaveTitle('Lychee — Peel back your pull requests');
    expect(consoleErrors).toEqual([]);
  });

  test('clicking the Setup nav link smooth-scrolls to the section and updates the URL hash', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('link', { name: 'Setup' }).first().click();

    await expect(page).toHaveURL(/#setup$/);
    await expect(page.locator('#setup')).toBeInViewport();
  });

  test('scroll-spy updates the active nav link as the page scrolls through sections', async ({ page }) => {
    await page.goto('/');

    const howItWorksLink = page.getByRole('link', { name: 'How It Works' }).first();
    const contributeLink = page.getByRole('link', { name: 'Contribute' }).first();

    await expect(howItWorksLink).not.toHaveAttribute('aria-current', 'true');

    await page.locator('#how-it-works').scrollIntoViewIfNeeded();
    await expect(howItWorksLink).toHaveAttribute('aria-current', 'true');

    await page.locator('#contribute').scrollIntoViewIfNeeded();
    await expect(contributeLink).toHaveAttribute('aria-current', 'true');
    await expect(howItWorksLink).not.toHaveAttribute('aria-current', 'true');
  });

  test('the ripeness badges carry the one-shot pulse class on load', async ({ page }) => {
    await page.goto('/');
    const badge = page.locator('#hero').getByText('🟢 Ripe', { exact: true });
    await expect(badge).toHaveClass(/badge-pulse/);
  });
});

test.describe('Mobile audit (375px)', () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test('has no horizontal overflow on the body', async ({ page }) => {
    await page.goto('/');

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.body.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));

    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });

  test('the hamburger toggles the mobile menu', async ({ page }) => {
    await page.goto('/');

    const toggle = page.getByLabel('Toggle navigation menu');
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });

  test('the deployment table sits in a horizontally scrollable wrapper rather than overflowing the page', async ({ page }) => {
    await page.goto('/');

    const table = page.locator('#how-it-works table').first();
    await table.scrollIntoViewIfNeeded();

    const wrapperOverflowX = await table.evaluate((el) => {
      const wrapper = el.parentElement;
      return wrapper ? getComputedStyle(wrapper).overflowX : null;
    });

    expect(wrapperOverflowX).toBe('auto');

    const bodyScrollWidth = await page.evaluate(() => document.body.scrollWidth);
    const viewportWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(bodyScrollWidth).toBeLessThanOrEqual(viewportWidth);
  });
});
