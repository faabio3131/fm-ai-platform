import { expect, test } from '@playwright/test';
import { waitForAppReady } from './fixtures/ui';

test('opens the FM AI Platform home page', async ({ page }) => {
  const errors: string[] = [];

  page.on('pageerror', (error) => {
    errors.push(error.message);
  });

  await waitForAppReady(page);

  await expect(page.locator('[data-testid="stMain"]')).toBeVisible();
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
  await expect(page.locator('body')).toContainText('Modo de teste isolado ativo');
  await expect(page).toHaveTitle(/.+/);
  expect(errors, 'page should not raise fatal JavaScript errors while loading').toEqual([]);
});
