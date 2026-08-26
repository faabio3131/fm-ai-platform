import { expect, test } from '@playwright/test';
import { dbNumber, realDbSnapshot, resetTestDb, waitForTestDb } from './fixtures/db';
import {
  clickAndWaitForStreamlitRerun,
  expectNoFatal,
  fillNumber,
  openTab,
  selectComboboxOption,
  waitForAppReady,
} from './fixtures/ui';

test.beforeEach(async () => {
  resetTestDb();
  await waitForTestDb();
});

test('PIX sandbox e cartões finalizam sem campos de dinheiro/troco', async ({ page }) => {
  await waitForAppReady(page);
  let before = dbNumber('select count(*) from vendas');
  await openTab(page, 'Frente de Caixa');
  await selectComboboxOption(page, /Forma de Pagamento/, 'Pix (Gerar QR Code Instantâneo)');
  await expect(page.getByText(/Gateway Pix Automático/)).toBeVisible();
  await clickAndWaitForStreamlitRerun(page, /Finalizar Venda/);
  await expect.poll(() => dbNumber('select count(*) from vendas')).toBe(before + 1);

  for (const forma of ['Cartão de Crédito', 'Cartão de Débito']) {
    before = dbNumber('select count(*) from vendas');
    await openTab(page, 'Frente de Caixa');
    await selectComboboxOption(page, /Forma de Pagamento/, forma);
    await expect(page.locator('body')).not.toContainText('Valor recebido do cliente');
    await expect(page.locator('body')).not.toContainText('Troco:');
    await clickAndWaitForStreamlitRerun(page, /Finalizar Venda/);
    await expect.poll(() => dbNumber('select count(*) from vendas')).toBe(before + 1);
  }
  await expectNoFatal(page);
});

test('Estoque cadastra insumo, bloqueia duplicidade e impede venda sem saldo', async ({ page }) => {
  await waitForAppReady(page);
  await openTab(page, 'Estoque & Validades');
  await page.getByRole('tab', { name: /Cadastrar Insumos/ }).click();
  await page.getByRole('button', { name: /Salvar Insumo/ }).click();
  await expect(page.getByText(/nome do insumo não pode estar vazio/i)).toBeVisible();
  const name = `Insumo E2E ${Date.now()}`;
  await page.getByLabel(/Nome do Insumo/).fill(name);
  await fillNumber(page, /Quantidade Inicial/, '1');
  await fillNumber(page, /Estoque Mínimo/, '1');
  await fillNumber(page, /Custo Unitário/, '3');
  await page.getByRole('button', { name: /Salvar Insumo/ }).click();
  await expect.poll(() => dbNumber(`select count(*) from insumos where nome='${name}'`)).toBe(1);

  await page.getByLabel(/Nome do Insumo/).fill(name);
  await page.getByRole('button', { name: /Salvar Insumo/ }).click();
  await expect(page.getByText(/Já existe um insumo/)).toBeVisible();

  await openTab(page, 'Frente de Caixa');
  const stockBefore = dbNumber("select saldo_atual from insumos where nome='Carne Teste'");
  const salesBefore = dbNumber('select count(*) from vendas');
  await fillNumber(page, /Quantidade de Itens/, '9999');
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
  await expect(page.getByText(/Estoque insuficiente/)).toBeVisible();
  expect(dbNumber('select count(*) from vendas')).toBe(salesBefore);
  expect(dbNumber("select saldo_atual from insumos where nome='Carne Teste'")).toBe(stockBefore);
});

test('Dashboard usa total da venda e Assistente de Atendimento permanece fail-closed sem fallback legado', async ({ page }) => {
  await waitForAppReady(page);
  await openTab(page, 'Dashboard Financeiro');
  await expect(page.getByText(/Faturamento Bruto/)).toBeVisible();
  await expect(page.locator('[data-testid="stMetricValue"]:visible').first()).toBeVisible();

  const beforeRevenue = dbNumber('select sum(valor_total) from vendas');
  await openTab(page, 'Frente de Caixa');
  await selectComboboxOption(page, /Forma de Pagamento/, 'Dinheiro Em Espécie');
  await fillNumber(page, /Valor recebido do cliente/, '100');
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
  await expect.poll(() => dbNumber('select sum(valor_total) from vendas')).toBeGreaterThan(beforeRevenue);
  const afterRevenue = dbNumber('select sum(valor_total) from vendas');
  expect(afterRevenue).toBeGreaterThan(beforeRevenue);
  expect(afterRevenue - beforeRevenue).toBeLessThan(100);

  await openTab(page, 'Assistente de Atendimento');
  await expect(page.getByRole('heading', { name: /Atendimento seguro V1$/ })).toBeVisible();
  await expect(
    page.getByText(
      /O Assistente de Atendimento está desativado neste ambiente.*fluxo legado de venda automática foi removido por segurança/,
    ),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: /Processar Pedido/ })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Atendimento comercial finalizado');
  await expect(page.locator('body')).not.toContainText('GEMINI_API_KEY');
  await expectNoFatal(page);
});

test('Modo E2E não cria nem modifica banco real', async ({ page }) => {
  const before = realDbSnapshot();
  await waitForAppReady(page);
  await openTab(page, 'Dashboard Financeiro');
  await expect(page.getByText(/Dashboard Financeiro/).last()).toBeVisible();
  expect(realDbSnapshot()).toEqual(before);
});
