import { expect, test } from '@playwright/test';

test('opens the FM AI Platform home page', async ({ page }) => {
  const errors: string[] = [];

  page.on('pageerror', (error) => {
    errors.push(error.message);
  });

  const response = await page.goto('/', { waitUntil: 'domcontentloaded' });

  expect(response, 'application should return a page response').not.toBeNull();
  expect(response?.ok(), 'application page response should be successful').toBe(true);
  await expect(page).toHaveTitle(/.+/);
  expect(errors, 'page should not raise fatal JavaScript errors while loading').toEqual([]);
});
