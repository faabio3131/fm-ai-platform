import { expect, test, type Page } from '@playwright/test';

async function marcarCheckbox(page: Page, nome: string) {
  const pronto = page.locator('[data-fm-ai-e2e-ready="true"]');
  const execucaoAnterior = Number(await pronto.getAttribute('data-fm-ai-e2e-run'));
  const checkbox = page.getByRole('checkbox', { name: nome });

  await checkbox.evaluate((elemento: HTMLInputElement) => {
    if (!elemento.checked) elemento.click();
  });

  await expect.poll(async () => Number(await pronto.getAttribute('data-fm-ai-e2e-run'))).toBeGreaterThan(
    execucaoAnterior,
  );
  await expect(page.getByRole('checkbox', { name: nome })).toBeChecked();
}

test('expedicao conclui checklist e atribui entregador sem acessar financeiro', async ({ page }) => {
  await page.goto('/?papel=expedicao');
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveAttribute(
    'data-fm-ai-e2e-papel',
    'expedicao',
  );
  await expect(page.getByRole('heading', { name: 'Expedição e Entrega' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Pedido pedido-exp' })).toBeVisible();

  await marcarCheckbox(page, 'Itens conferidos · pedido-exp');
  await marcarCheckbox(page, 'Embalagem conferida · pedido-exp');
  await marcarCheckbox(page, 'Identificação conferida · pedido-exp');
  await page.getByRole('button', { name: 'Concluir checklist · pedido-exp' }).click();

  await expect(page.getByRole('button', { name: 'Concluir checklist · pedido-exp' })).toHaveCount(0);
  await expect(page.getByText('Status: aguardando_entregador', { exact: true })).toBeVisible();

  await page.getByRole('textbox', { name: 'ID do entregador · pedido-exp' }).fill('driver-2');
  await page.getByRole('button', { name: 'Atribuir entregador · pedido-exp' }).click();

  await expect(page.getByRole('button', { name: 'Atribuir entregador · pedido-exp' })).toHaveCount(0);
  await expect(page.getByText('Entregador: driver-2', { exact: true })).toBeVisible();
});
