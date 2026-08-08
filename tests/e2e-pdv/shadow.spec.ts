import { expect, test } from '@playwright/test';
import { dbNumber } from '../e2e/fixtures/db';
import { fillNumber, openTab, selectComboboxOption, waitForAppReady } from '../e2e/fixtures/ui';

test('shadow persiste Pedido sem duplicar efeitos legados', async ({ page }) => {
  await waitForAppReady(page);
  const vendas = dbNumber('select count(*) from vendas');
  const estoque = dbNumber("select saldo_atual from insumos where nome='Carne Teste'");
  await openTab(page, 'Frente de Caixa');
  await fillNumber(page, /Quantidade de Itens/, '1');
  await selectComboboxOption(page, /Forma de Pagamento/, 'Dinheiro Em Espécie');
  await fillNumber(page, /Valor recebido do cliente/, '50');
  await page.getByRole('button', { name: /Finalizar Venda/ }).click();
  await expect.poll(() => dbNumber('select count(*) from vendas')).toBe(vendas + 1);
  expect(dbNumber('select count(*) from pedidos_v1')).toBe(1);
  expect(dbNumber("select count(*) from sqlite_master where type='table' and name='vendas_financeiras_v1'")).toBe(0);
  expect(dbNumber("select saldo_atual from insumos where nome='Carne Teste'")).toBe(estoque - 1);
  expect(dbNumber("select count(*) from pdv_reconciliacoes_v1 where modo='shadow' and status='conciliado'")).toBe(1);
});
