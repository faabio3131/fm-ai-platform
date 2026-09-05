import { expect, type Locator, type Page, test } from '@playwright/test';

async function selecionarCombo(combo: Locator, opcao: string) {
  await expect(combo).toBeVisible();
  await expect(combo).toBeEnabled();
  if ((await combo.inputValue()) === opcao) {
    return;
  }
  await expect(async () => {
    await combo.click();
    const option = combo
      .page()
      .getByRole('option', { name: opcao, exact: true })
      .filter({ visible: true })
      .last();
    await expect(option).toBeVisible({ timeout: 5_000 });
    await option.click();
    await expect(combo).toHaveValue(opcao, { timeout: 5_000 });
  }).toPass({ timeout: 20_000 });
}

async function selecionarCliente(page: Page, clienteId: string) {
  const combo = page.getByRole('combobox', { name: /Cliente CRM/ }).first();
  await selecionarCombo(combo, clienteId);
  await expect(page.getByText(/Endereço validado:/)).toBeVisible();
}

async function selecionarFormaPagamento(page: Page, opcao: string) {
  const combo = page.getByRole('combobox', { name: /Forma de pagamento/ }).first();
  await selecionarCombo(combo, opcao);
}

async function iniciarCarrinhoComProduto(page: Page) {
  await page.getByRole('button', { name: /Iniciar novo pedido/ }).click();
  await expect(page.getByRole('heading', { name: /1\. Cardápio/ })).toBeVisible();
  await expect(page.getByText('Burger Delivery Comercial', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Adicionar', exact: true }).click();
  await expect(page.getByText(/1x Burger Delivery Comercial/)).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Delivery Próprio/ })).toBeVisible();
  await expect(page.getByText(/definido pela identidade autenticada/)).toBeVisible();
});

test('cliente autenticado conclui jornada própria pelo checkout e entrega canônicos', async ({ page }) => {
  await selecionarCliente(page, 'cliente-delivery-a');
  await iniciarCarrinhoComProduto(page);

  await page
    .getByRole('button', { name: /Calcular taxa e SLA no endereço validado/ })
    .click();
  await expect(page.getByText(/Centro E2E: taxa R\$ 7\.00/)).toBeVisible();

  await expect(page.getByRole('button', { name: /Aplicar cupom/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Reservar cashback/ })).toHaveCount(0);
  await expect(page.getByText(/Cupom e cashback não são fabricados pela UI/)).toBeVisible();

  await selecionarFormaPagamento(page, 'Pix');
  await page.getByRole('button', { name: /Confirmar pedido/ }).click();

  await expect(page.getByRole('heading', { name: /4\. Acompanhamento/ })).toBeVisible();
  await expect(page.getByText(/Pedido: aguardando_confirmacao/)).toBeVisible();
  await expect(page.getByText(/Entrega: aguardando_producao/)).toBeVisible();
  await expect(page.getByText(/Total canônico/)).toBeVisible();
});

test('endereço CRM validado fora da área falha fechado sem confirmar pedido', async ({ page }) => {
  await selecionarCliente(page, 'cliente-delivery-b');
  await expect(page.getByText(/CEP 99999999/)).toBeVisible();
  await iniciarCarrinhoComProduto(page);

  await page
    .getByRole('button', { name: /Calcular taxa e SLA no endereço validado/ })
    .click();
  await expect(page.getByText(/fora_da_area_de_entrega/)).toBeVisible();
  await expect(page.getByRole('heading', { name: /4\. Acompanhamento/ })).toHaveCount(0);
});

test('pagamento na entrega permanece cancelável e reconcilia pedido e logística', async ({ page }) => {
  await selecionarCliente(page, 'cliente-delivery-c');
  await iniciarCarrinhoComProduto(page);
  await page
    .getByRole('button', { name: /Calcular taxa e SLA no endereço validado/ })
    .click();
  await expect(page.getByText(/Centro E2E: taxa R\$ 7\.00/)).toBeVisible();

  await selecionarFormaPagamento(page, 'Pagamento na entrega');
  await page.getByRole('button', { name: /Confirmar pedido/ }).click();
  await expect(page.getByRole('heading', { name: /4\. Acompanhamento/ })).toBeVisible();
  await expect(page.getByText(/Entrega: aguardando_producao/)).toBeVisible();

  await page.getByText('Cancelar pedido', { exact: true }).click();
  await page.getByLabel('Motivo').fill('Solicitação E2E do cliente');
  await page.getByRole('button', { name: /Cancelar no fluxo canônico/ }).click();

  await expect(page.getByText(/Pedido: cancelado/)).toBeVisible();
  await expect(page.getByText(/Entrega: cancelada/)).toBeVisible();
});
