import { expect, test } from '@playwright/test';
import { openTab, waitForAppReady } from './fixtures/ui';

const tabTexts = [
  'Engenharia de Cardápio',
  'CRM, Resgate & Cashback',
  'Frente de Caixa',
  'Estoque & Validades',
  'Dashboard Financeiro',
  'Bot Cliente',
];

if (process.env.FM_AI_KDS_V1 === '1') {
  tabTexts.push('KDS por Setor');
}
if (process.env.FM_AI_SALAO_V1 === '1') {
  tabTexts.push('Mesas e Comandas');
}


test('carrega e navega por todas as abas reais em modo de teste', async ({ page }) => {
  const jsErrors: string[] = [];
  page.on('pageerror', error => jsErrors.push(error.message));
  await waitForAppReady(page);
  await expect(page.locator('[data-testid="stTabs"]').first()).toBeVisible();
  for (const text of tabTexts) {
    await openTab(page, text);
  }
  await expect(page.locator('body')).not.toContainText('Traceback');
  await expect(page.locator('body')).not.toContainText('GEMINI_API_KEY');
  await expect(page.locator('body')).not.toContainText('Choose an option');
  expect(jsErrors).toEqual([]);
});
