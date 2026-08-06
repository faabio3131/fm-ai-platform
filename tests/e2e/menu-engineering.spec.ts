import { expect, test } from '@playwright/test';
import { dbNumber, realDbSnapshot, resetTestDb, waitForTestDb } from './fixtures/db';
import { expectNoFatal, fillNumber, openTab, waitForAppReady } from './fixtures/ui';

test.beforeEach(async () => {
  resetTestDb();
  await waitForTestDb();
});

test('Engenharia cadastra prato com ficha técnica no banco temporário', async ({ page }) => {
  const before = realDbSnapshot();
  await waitForAppReady(page);
  await openTab(page, 'Engenharia de Cardápio');
  await page.getByRole('button', { name: /Salvar Prato/ }).click();
  await expect(page.getByText('Digite o nome do prato')).toBeVisible();

  const dish = `Prato E2E ${Date.now()}`;
  await page.getByLabel('Nome do Prato / Lanche').fill(dish);
  await page.getByLabel('Selecione o Insumo do Almoxarifado').click();
  await page.getByText(/Carne Teste|Hambúrguer 180g Angus/).first().click();
  await fillNumber(page, /Quantidade/, '2');
  await page.getByRole('button', { name: /Adicionar à Receita/ }).click();
  await expect(page.getByText('Receita Montada')).toBeVisible();
  await fillNumber(page, 'Preço de Venda Final (R$)', '42.50');
  await page.getByRole('button', { name: /Salvar Prato/ }).click();
  await expect.poll(() => dbNumber(`select count(*) from produtos where nome='${dish}'`)).toBe(1);
  expect(dbNumber(`select count(*) from fichas_tecnicas ft join produtos p on p.id=ft.produto_id where p.nome='${dish}'`)).toBe(1);
  expect(realDbSnapshot()).toEqual(before);
  await expectNoFatal(page);
});

test('Importação IA usa mock, trata JSON inválido e erro 429 sem gravação parcial', async ({ page }) => {
  await waitForAppReady(page);
  await openTab(page, 'Engenharia de Cardápio');
  await page.getByText(/Importação Automática de Cardápio via IA/).click();
  await page.getByText(/Colar Texto do Cardápio/).click();
  const before = dbNumber('select count(*) from produtos');
  await page.getByLabel(/Cole aqui o texto/).fill('Cardápio E2E previsível');
  await page.getByRole('button', { name: /Processar Cardápio/ }).click();
  await expect(page.getByText(/2 pratos/)).toBeVisible();
  expect(dbNumber("select count(*) from produtos where nome like '%IA Teste%'" )).toBeGreaterThanOrEqual(2);

  const afterSuccess = dbNumber('select count(*) from produtos');
  await page.getByLabel(/Cole aqui o texto/).fill('FM_AI_MOCK_INVALID');
  await page.getByRole('button', { name: /Processar Cardápio/ }).click();
  await expect(page.getByText(/Erro ao processar cardápio/)).toBeVisible();
  expect(dbNumber('select count(*) from produtos')).toBe(afterSuccess);

  await page.getByLabel(/Cole aqui o texto/).fill('FM_AI_MOCK_429');
  await page.getByRole('button', { name: /Processar Cardápio/ }).click();
  await expect(page.getByText(/erro 429|Erro ao processar cardápio/i)).toBeVisible();
  await expect(page.locator('body')).not.toContainText('AIza');
  expect(dbNumber('select count(*) from produtos')).toBe(afterSuccess);
  expect(afterSuccess).toBeGreaterThan(before);
});
