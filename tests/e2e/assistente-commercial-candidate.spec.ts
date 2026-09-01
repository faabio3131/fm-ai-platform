import { expect, test } from '@playwright/test';
import { openTab, waitForAppReady } from './fixtures/ui';

test('candidato Fase 4 abre Assistente real no navegador sem fallback legado', async ({ page }) => {
  const jsErrors: string[] = [];
  page.on('pageerror', error => jsErrors.push(error.message));

  await waitForAppReady(page);
  await openTab(page, 'Assistente de Atendimento');

  const painel = page.getByRole('tabpanel', { name: /Assistente de Atendimento/ });

  await expect(
    painel.getByRole('heading', { name: /Funcionário Digital V1/ }),
  ).toBeVisible();
  await expect(
    painel.getByRole('textbox', { name: 'WhatsApp do cliente' }),
  ).toBeVisible();
  await expect(
    painel.getByRole('radiogroup', { name: 'Entrada do cliente' }),
  ).toBeVisible();
  await expect(
    painel.getByRole('textbox', { name: 'Mensagem do cliente' }),
  ).toBeVisible();
  await expect(
    painel.getByRole('button', { name: /Analisar com/ }),
  ).toBeVisible();

  await painel.getByRole('button', { name: /Analisar com/ }).click();
  await expect(
    painel.getByText(/WhatsApp e conteúdo de atendimento são obrigatórios/),
  ).toBeVisible();

  await painel.getByText('Áudio', { exact: true }).click();
  await expect(
    painel.getByText('Áudio do cliente', { exact: true }),
  ).toBeVisible();

  await expect(
    painel.getByRole('button', { name: /Processar Pedido/ }),
  ).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('OperacaoMicaFake');
  await expect(page.locator('body')).not.toContainText('Traceback');
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  expect(jsErrors).toEqual([]);
});
