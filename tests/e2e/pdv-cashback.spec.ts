import { expect, test } from '@playwright/test';
import { dbNumber } from './fixtures/db';
import { expectNoFatal, fillNumber, openTab } from './fixtures/ui';

async function sellCash(page, quantity: string, received: string, clientName?: RegExp) {
  await openTab(page, 'Frente de Caixa');
  await fillNumber(page, /Quantidade de Itens/, quantity);
  if (clientName) {
    await page.getByLabel(/Identificar Cliente/).click();
    await page.getByText(clientName).click();
  }
  await page.getByLabel(/Forma de Pagamento/).click();
  await page.getByText('Dinheiro Em Espécie').click();
  await fillNumber(page, /Valor recebido do cliente/, received);
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
}

test('CRM cadastra cliente E2E, evita duplicidade e integra cashback ao PDV', async ({ page }) => {
  await page.goto('/');
  await openTab(page, 'CRM, Resgate & Cashback');
  await page.getByRole('tab', { name: /Cashback/ }).click();
  await page.getByRole('button', { name: /Salvar Cliente E2E/ }).click();
  await expect(page.getByText(/obrigatórios/)).toBeVisible();

  const suffix = Date.now();
  const name = `Cliente Cashback E2E ${suffix}`;
  const phone = `5511988${String(suffix).slice(-6)}`;
  await page.getByLabel('Nome do Cliente E2E').fill(name);
  await page.getByLabel('WhatsApp do Cliente E2E').fill(phone);
  await page.getByRole('button', { name: /Salvar Cliente E2E/ }).click();
  await expect(page.getByText(name)).toBeVisible();
  expect(dbNumber(`select count(*) from clientes where whatsapp='${phone}'`)).toBe(1);

  await page.getByLabel('Nome do Cliente E2E').fill(name);
  await page.getByLabel('WhatsApp do Cliente E2E').fill(phone);
  await page.getByRole('button', { name: /Salvar Cliente E2E/ }).click();
  await expect(page.getByText(/já cadastrado/)).toBeVisible();

  const salesBefore = dbNumber('select count(*) from vendas');
  await sellCash(page, '1', '50', new RegExp(name));
  await expect(page.getByText(/Venda finalizada com sucesso|Venda registrada com sucesso/)).toBeVisible();
  expect(dbNumber('select count(*) from vendas')).toBe(salesBefore + 1);
  expect(dbNumber(`select saldo_cashback from clientes where whatsapp='${phone}'`)).toBeGreaterThan(0);

  await sellCash(page, '1', '50', new RegExp(name));
  await expect(page.getByText(/Venda finalizada com sucesso|Venda registrada com sucesso/)).toBeVisible();
  expect(dbNumber(`select saldo_cashback from clientes where whatsapp='${phone}'`)).toBeGreaterThanOrEqual(0);

  const balcBefore = dbNumber("select count(*) from clientes where nome like '%Balcão%'");
  await sellCash(page, '1', '50');
  expect(dbNumber("select count(*) from clientes where nome like '%Balcão%'")).toBe(balcBefore);
  await expectNoFatal(page);
});

test('PDV dinheiro bloqueia insuficiente, preserva dados, finaliza uma vez e reseta', async ({ page }) => {
  await page.goto('/');
  const salesBefore = dbNumber('select count(*) from vendas');
  const stockBefore = dbNumber("select saldo_atual from insumos where nome='Carne Teste'");
  await openTab(page, 'Frente de Caixa');
  await fillNumber(page, /Quantidade de Itens/, '3');
  await page.getByLabel(/Forma de Pagamento/).click();
  await page.getByText('Dinheiro Em Espécie').click();
  await fillNumber(page, /Valor recebido do cliente/, '1');
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
  await expect(page.getByText(/Pagamento insuficiente/)).toBeVisible();
  await expect(page.getByLabel(/Quantidade de Itens/)).toHaveValue('3');
  expect(dbNumber('select count(*) from vendas')).toBe(salesBefore);
  expect(dbNumber("select saldo_atual from insumos where nome='Carne Teste'")).toBe(stockBefore);

  await fillNumber(page, /Valor recebido do cliente/, '100');
  await expect(page.getByText(/Troco: R\$/)).toBeVisible();
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
  await expect(page.getByText(/Venda finalizada com sucesso|Venda registrada com sucesso/)).toBeVisible();
  expect(dbNumber('select count(*) from vendas')).toBe(salesBefore + 1);
  expect(dbNumber("select saldo_atual from insumos where nome='Carne Teste'")).toBe(stockBefore - 3);
  await expect(page.getByLabel(/Quantidade de Itens/)).toHaveValue('1');
  await expect(page.locator('body')).not.toContainText('Troco:');
  await expectNoFatal(page);
});
