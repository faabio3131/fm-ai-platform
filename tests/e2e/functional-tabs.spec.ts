import { expect, test } from '@playwright/test';

const tabTexts = [
  'Engenharia de Cardápio',
  'CRM, Resgate & Cashback',
  'Frente de Caixa',
  'Estoque & Validades',
  'Dashboard Financeiro',
  'Bot Cliente',
];

test('carrega e navega por todas as abas reais em modo de teste', async ({ page }) => {
  const jsErrors: string[] = [];
  page.on('pageerror', error => jsErrors.push(error.message));
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('F&M AI FOOD')).toBeVisible();
  await expect(page.getByText('Modo de teste isolado ativo')).toBeVisible();
  for (const text of tabTexts) {
    await page.getByRole('tab', { name: new RegExp(text) }).click();
    await expect(page.getByText(new RegExp(text.split(' ')[0]))).toBeVisible();
  }
  await expect(page.locator('body')).not.toContainText('Traceback');
  await expect(page.locator('body')).not.toContainText('GEMINI_API_KEY');
  await expect(page.locator('body')).not.toContainText('Choose an option');
  expect(jsErrors).toEqual([]);
});
