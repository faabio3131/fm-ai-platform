import { expect, test } from '@playwright/test';

test('expedicao conclui checklist e atribui entregador sem acessar financeiro', async ({ page }) => {
  await page.goto('/?papel=expedicao');
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveAttribute(
    'data-fm-ai-e2e-papel',
    'expedicao',
  );
  await expect(page.getByRole('heading', { name: 'Expedição e Entrega' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Pedido pedido-exp' })).toBeVisible();

  await page.getByRole('checkbox', { name: 'Itens conferidos · pedido-exp' }).check();
  await page.getByRole('checkbox', { name: 'Embalagem conferida · pedido-exp' }).check();
  await page.getByRole('checkbox', { name: 'Identificação conferida · pedido-exp' }).check();
  await page.getByRole('button', { name: 'Concluir checklist · pedido-exp' }).click();

  await expect(page.getByRole('button', { name: 'Concluir checklist · pedido-exp' })).toHaveCount(0);
  await expect(page.getByText('Status: aguardando_entregador', { exact: true })).toBeVisible();

  await page.getByRole('textbox', { name: 'ID do entregador · pedido-exp' }).fill('driver-2');
  await page.getByRole('button', { name: 'Atribuir entregador · pedido-exp' }).click();

  await expect(page.getByRole('button', { name: 'Atribuir entregador · pedido-exp' })).toHaveCount(0);
  await expect(page.getByText('Entregador: driver-2', { exact: true })).toBeVisible();
});
