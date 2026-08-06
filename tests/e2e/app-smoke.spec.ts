import { expect, test } from '@playwright/test';
import { waitForAppReady } from './fixtures/ui';

test('opens the FM AI Platform home page', async ({ page }) => {
  const errors: string[] = [];

  page.on('pageerror', (error) => {
    errors.push(error.message);
  });

  await waitForAppReady(page);

  await expect(page.locator('[data-testid="stTabs"]').first()).toBeVisible();
  await expect(page).toHaveTitle(/.+/);
  expect(errors, 'page should not raise fatal JavaScript errors while loading').toEqual([]);
});
