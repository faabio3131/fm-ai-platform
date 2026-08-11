import { expect, test } from '@playwright/test';

async function abrirEntregador(page) {
  await page.goto('/?papel=entregador');
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveAttribute(
    'data-fm-ai-e2e-papel',
    'entregador',
  );
}

test('entregador conclui custodia somente com financeiro resolvido', async ({ page }) => {
  await abrirEntregador(page);
  await expect(page.getByRole('heading', { name: 'Pedido pedido-paid' })).toBeVisible();

  await page.getByRole('button', { name: 'Confirmar coleta · pedido-paid' }).click();
  await expect(page.getByRole('button', { name: 'Sair em rota · pedido-paid' })).toBeVisible();
  await page.getByRole('button', { name: 'Sair em rota · pedido-paid' }).click();
  await expect(page.getByRole('button', { name: 'Confirmar entrega · pedido-paid' })).toBeVisible();
  await page.getByRole('button', { name: 'Confirmar entrega · pedido-paid' }).click();

  await expect(page.getByRole('button', { name: 'Confirmar entrega · pedido-paid' })).toHaveCount(0);
  await expect(page.getByText('Status: entregue', { exact: true })).toBeVisible();
});

test('entrega nao transforma aguardando_entrega em pagamento confirmado', async ({ page }) => {
  await abrirEntregador(page);
  await expect(page.getByRole('heading', { name: 'Pedido pedido-pending' })).toBeVisible();

  await page.getByRole('button', { name: 'Confirmar coleta · pedido-pending' }).click();
  await page.getByRole('button', { name: 'Sair em rota · pedido-pending' }).click();
  await page.getByRole('button', { name: 'Confirmar entrega · pedido-pending' }).click();

  await expect(page.getByText('Operação recusada: criterio_financeiro_pendente')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirmar entrega · pedido-pending' })).toBeVisible();
  await expect(page.getByText('Status: em_rota', { exact: true })).toBeVisible();
});
