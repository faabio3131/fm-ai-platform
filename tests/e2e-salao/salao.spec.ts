import { expect, test, type Page } from '@playwright/test';

import {
  clickAndWaitForStreamlitRerun,
  fillNumber,
  selectComboboxOption,
} from '../e2e/fixtures/ui';

async function abrirSalao(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Salao E2E pronto', { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole('heading', { name: /Mesas e Comandas/ })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveCount(1, {
    timeout: 30_000,
  });
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, {
    timeout: 30_000,
  });
}

test('salao abre mesa agrega pedidos transfere divide pagamento e fecha', async ({ page }) => {
  await abrirSalao(page);

  await selectComboboxOption(page, 'Mesa', 'Mesa 01');
  await expect(page.getByText('Status: livre', { exact: false })).toBeVisible();
  await clickAndWaitForStreamlitRerun(page, 'Abrir comanda');
  await expect(page.getByText('Status: aberta', { exact: false })).toBeVisible();

  await clickAndWaitForStreamlitRerun(page, 'Adicionar pedido');
  await expect(page.getByText('R$ 40.00', { exact: false }).first()).toBeVisible();

  await clickAndWaitForStreamlitRerun(page, 'Adicionar pedido');
  await expect(page.getByText('R$ 70.00', { exact: false }).first()).toBeVisible();

  await selectComboboxOption(page, 'Transferir para', 'Mesa 02');
  await clickAndWaitForStreamlitRerun(page, 'Transferir comanda');
  await selectComboboxOption(page, 'Mesa', 'Mesa 02');
  await expect(page.getByText('Status: ocupada', { exact: false })).toBeVisible();

  await clickAndWaitForStreamlitRerun(page, 'Solicitar conta');
  await expect(page.getByText('Status: conta_solicitada', { exact: false })).toBeVisible();

  await clickAndWaitForStreamlitRerun(page, 'Retomar consumo');
  await expect(page.getByText('Status: em_consumo', { exact: false })).toBeVisible();
  await clickAndWaitForStreamlitRerun(page, 'Solicitar conta');
  await expect(page.getByText('Status: conta_solicitada', { exact: false })).toBeVisible();

  await fillNumber(page, 'Valor PIX', '40.00');
  await clickAndWaitForStreamlitRerun(page, 'Definir pagamento misto');
  await expect(
    page.getByText(/Status:\s*fechamento_em_andamento/).first(),
  ).toBeVisible();

  await expect(page.getByText(/Próxima parcela: pix · R\$ 40\.00/)).toBeVisible();
  await page.getByRole('textbox', { name: 'ID do pagamento canônico já confirmado' }).fill('e2e-pay-pix');
  await clickAndWaitForStreamlitRerun(page, 'Vincular pagamento confirmado');
  await expect(page.getByText(/Status:\s*parcialmente_paga/).first()).toBeVisible();
  await expect(page.getByText(/Próxima parcela: dinheiro · R\$ 30\.00/)).toBeVisible();
  await page.getByRole('textbox', { name: 'ID do pagamento canônico já confirmado' }).fill('e2e-pay-cash');
  await clickAndWaitForStreamlitRerun(page, 'Vincular pagamento confirmado');
  await expect(page.getByText('Saldo integralmente confirmado.', { exact: true })).toBeVisible();

  await clickAndWaitForStreamlitRerun(page, 'Fechar comanda');
  await expect(page.getByText('Status: livre', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Abrir comanda', exact: true })).toBeVisible();
});


test('salao cancela comanda vazia e libera a mesa', async ({ page }) => {
  await abrirSalao(page);
  await selectComboboxOption(page, 'Mesa', 'Mesa 03');
  await clickAndWaitForStreamlitRerun(page, 'Abrir comanda');
  await expect(page.getByText('Status: aberta', { exact: false })).toBeVisible();
  await clickAndWaitForStreamlitRerun(page, 'Cancelar comanda');
  await expect(page.getByText('Status: livre', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Abrir comanda', exact: true })).toBeVisible();
});
