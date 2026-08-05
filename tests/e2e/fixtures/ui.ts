import { expect, type Page } from '@playwright/test';

export async function openTab(page: Page, name: string) {
  await page.getByRole('tab', { name: new RegExp(name) }).click();
}

export async function expectNoFatal(page: Page) {
  await expect(page.locator('body')).not.toContainText('Traceback');
  await expect(page.locator('body')).not.toContainText('GEMINI_API_KEY');
}

export async function fillNumber(page: Page, label: string | RegExp, value: string) {
  const input = page.getByLabel(label).first();
  await input.fill(value);
}
