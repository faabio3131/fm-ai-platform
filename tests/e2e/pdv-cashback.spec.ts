import { expect, test } from '@playwright/test';
import { dbNumber, resetTestDb, waitForTestDb } from './fixtures/db';
import { expectNoFatal, fillNumber, openTab, selectComboboxOption, waitForAppReady } from './fixtures/ui';

async function sellCash(page, quantity: string, received: string, clientName?: RegExp) {
  await openTab(page, 'Frente de Caixa');
  await fillNumber(page, /Quantidade de Itens/, quantity);
  if (clientName) {
    await selectComboboxOption(page, /Identificar Cliente/, clientName);
  }
  const payment = page.getByRole('combobox', { name: /Forma de Pagamento/ }).first();
  const receivedInput = page.getByRole('spinbutton', { name: /Valor recebido do cliente/ }).first();
  await expect(async () => {
    await selectComboboxOption(page, /Forma de Pagamento/, 'Dinheiro Em Espécie');
    await expect(payment).toHaveValue('Dinheiro Em Espécie');
    await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0);
    await expect(receivedInput).toBeVisible();
    await expect(receivedInput).toBeEnabled();
  }).toPass({ timeout: 30_000 });
  await fillNumber(page, /Valor recebido do cliente/, received);
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
}

test.beforeEach(async () => {
  resetTestDb();
  await waitForTestDb();
});

test('CRM cadastra cliente E2E, evita duplicidade e integra cashback ao PDV', async ({ page }) => {
  await waitForAppReady(page);
  await openTab(page, 'CRM, Resgate & Cashback');
  await page.getByRole('tab', { name: /Gestão de Fidelidade/ }).click();
  await page.getByRole('button', { name: /Salvar Cliente E2E/ }).click();
  await expect(page.getByText(/obrigatórios/)).toBeVisible();

  const suffix = Date.now();
  const name = `Cliente Cashback E2E ${suffix}`;
  const phone = `5511988${String(suffix).slice(-6)}`;
  await page.getByLabel('Nome do Cliente E2E').fill(name);
  await page.getByLabel('WhatsApp do Cliente E2E').fill(phone);
  await page.getByRole('button', { name: /Salvar Cliente E2E/ }).click();
  await expect.poll(() => dbNumber(`select count(*) from clientes where whatsapp='${phone}'`)).toBe(1);

  await page.getByLabel('Nome do Cliente E2E').fill(name);
  await page.getByLabel('WhatsApp do Cliente E2E').fill(phone);
  await page.getByRole('button', { name: /Salvar Cliente E2E/ }).click();
  await expect(page.getByText(/Cliente E2E já cadastrado/)).toBeVisible();

  const salesBefore = dbNumber('select count(*) from vendas');
  await sellCash(page, '1', '50', new RegExp(name));
  await expect.poll(() => dbNumber('select count(*) from vendas')).toBe(salesBefore + 1);
  expect(dbNumber(`select saldo_cashback from clientes where whatsapp='${phone}'`)).toBeGreaterThan(0);

  await sellCash(page, '1', '50', new RegExp(name));
  await expect.poll(() => dbNumber('select count(*) from vendas')).toBe(salesBefore + 2);
  expect(dbNumber(`select saldo_cashback from clientes where whatsapp='${phone}'`)).toBeGreaterThanOrEqual(0);

  const balcBefore = dbNumber("select count(*) from clientes where nome like '%Balcão%'");
  await sellCash(page, '1', '50');
  expect(dbNumber("select count(*) from clientes where nome like '%Balcão%'")).toBe(balcBefore);
  await expectNoFatal(page);
});

test('PDV dinheiro bloqueia insuficiente, preserva dados, finaliza uma vez e reseta', async ({ page }) => {
  await waitForAppReady(page);
  const salesBefore = dbNumber('select count(*) from vendas');
  const stockBefore = dbNumber("select saldo_atual from insumos where nome='Carne Teste'");
  await openTab(page, 'Frente de Caixa');
  await fillNumber(page, /Quantidade de Itens/, '3');
  await selectComboboxOption(page, /Forma de Pagamento/, 'Dinheiro Em Espécie');
  await fillNumber(page, /Valor recebido do cliente/, '1');
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
  await expect(page.getByText(/Pagamento insuficiente/)).toBeVisible();
  await expect(page.getByLabel(/Quantidade de Itens/)).toHaveValue('3');
  expect(dbNumber('select count(*) from vendas')).toBe(salesBefore);
  expect(dbNumber("select saldo_atual from insumos where nome='Carne Teste'")).toBe(stockBefore);

  await fillNumber(page, /Valor recebido do cliente/, '100');
  await expect(page.getByText(/Troco: R\$/)).toBeVisible();
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
  await expect.poll(() => dbNumber('select count(*) from vendas')).toBe(salesBefore + 1);
  expect(dbNumber("select saldo_atual from insumos where nome='Carne Teste'")).toBe(stockBefore - 3);
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
  await expect(page.getByRole('spinbutton', { name: /Quantidade de Itens/ })).toHaveValue('1');
  await expect(page.getByRole('combobox', { name: /Forma de Pagamento/ })).toHaveValue(
    'Pix (Gerar QR Code Instantâneo)',
  );
  await expect(page.getByRole('spinbutton', { name: /Valor recebido do cliente/ })).toHaveCount(0);
  await expectNoFatal(page);
});
