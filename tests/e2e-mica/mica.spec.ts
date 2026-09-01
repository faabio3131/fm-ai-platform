import { expect, test } from '@playwright/test';
import { openTab, waitForAppReady } from '../e2e/fixtures/ui';

test('cutover legado abre somente o Assistente canônico', async ({ page }) => {
  await waitForAppReady(page);
  await openTab(page, 'Assistente de Atendimento');

  await expect(page.getByRole('heading', { name: /Funcionário Digital V1$/ })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'WhatsApp do cliente' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Mensagem do cliente' })).toBeVisible();
  await expect(page.getByRole('radiogroup', { name: 'Entrada do cliente' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Processar Pedido/ })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('OperacaoMicaFake');
  await expect(page.locator('body')).not.toContainText('Traceback');
});

test('Assistente canônico falha fechado sem dados obrigatórios', async ({ page }) => {
  await waitForAppReady(page);
  await openTab(page, 'Assistente de Atendimento');

  await page.getByRole('button', { name: /Analisar com/ }).click();
  await expect(
    page.getByText(/WhatsApp e conteúdo de atendimento são obrigatórios/),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: /Processar Pedido/ })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
});
