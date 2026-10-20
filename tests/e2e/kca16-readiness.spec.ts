import { expect, test } from '@playwright/test';
import { waitForAppReady } from './fixtures/ui';

test('KCA-16 responsive functional baseline works on mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await waitForAppReady(page);

  const app = page.locator('[data-testid="stAppViewContainer"]').first();
  await expect(app).toBeVisible();
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');

  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth - root.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(2);

  const controls = page.locator('button:visible, input:visible, textarea:visible, select:visible');
  const count = await controls.count();
  for (let index = 0; index < count; index += 1) {
    const box = await controls.nth(index).boundingBox();
    if (box) {
      expect(box.width).toBeGreaterThan(0);
      expect(box.height).toBeGreaterThan(0);
    }
  }
});

test('KCA-16 desktop functional baseline has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await waitForAppReady(page);

  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  const overflow = await page.evaluate(() => {
    const root = document.documentElement;
    return root.scrollWidth - root.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(2);
});

test('KCA-16 application readiness performance baseline stays bounded', async ({ page }) => {
  const started = Date.now();
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveCount(1, {
    timeout: 45_000,
  });
  const readyMs = Date.now() - started;

  expect(readyMs).toBeLessThan(45_000);
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
});
