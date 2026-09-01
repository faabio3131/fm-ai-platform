import { expect, test } from '@playwright/test';
import { openTab, waitForAppReady } from './fixtures/ui';

test('candidato Fase 4 abre Assistente real no navegador sem fallback legado', async ({ page }) => {
  const jsErrors: string[] = [];
  page.on('pageerror', error => jsErrors.push(error.message));

  await waitForAppReady(page);
  await openTab(page, 'Assistente de Atendimento');

  await expect(
    page.getByRole('heading', { name: /Funcionário Digital V1/ }),
  ).toBeVisible();
  await expect(page.getByLabel('WhatsApp do cliente').first()).toBeVisible();
  await expect(page.getByText('Entrada do cliente', { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel('Mensagem do cliente').first()).toBeVisible();
  await expect(page.getByRole('button', { name: /Analisar com/ }).first()).toBeVisible();

  await page.getByRole('button', { name: /Analisar com/ }).first().click();
  await expect(
    page.getByText(/WhatsApp e conteúdo de atendimento são obrigatórios/),
  ).toBeVisible();

  await page.getByRole('radio', { name: 'Áudio' }).check();
  await expect(page.getByText('Áudio do cliente', { exact: true }).first()).toBeVisible();

  await expect(page.getByRole('button', { name: /Processar Pedido/ })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('OperacaoMicaFake');
  await expect(page.locator('body')).not.toContainText('Traceback');
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  expect(jsErrors).toEqual([]);
});
