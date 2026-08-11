import { expect, test, type Page } from '@playwright/test';

async function abrirGerente(page: Page) {
  await page.goto('/?papel=gerente', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Garcom E2E pronto', { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole('heading', { name: 'Atendimento do Garçom' })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveCount(1, {
    timeout: 30_000,
  });
  await expect(page.locator('[data-fm-ai-e2e-papel="gerente"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, {
    timeout: 30_000,
  });
}

test('gerente no tablet vê salão completo sem ganhar fluxo financeiro na UI do garçom', async ({ page }) => {
  await abrirGerente(page);

  expect(page.viewportSize()).toEqual({ width: 820, height: 1180 });
  await expect(page.getByText('Perfil ativo: gerente', { exact: false })).toBeVisible();

  await expect(page.getByText('Pedido pedido-garcom-1 pronto', { exact: false })).toBeVisible();
  await expect(page.getByText('Pedido pedido-garcom-2 pronto', { exact: false })).toBeVisible();
  await expect(page.getByText('Mesa 01 · ocupada', { exact: true })).toBeVisible();
  await expect(page.getByText('Mesa 02 · ocupada', { exact: true })).toBeVisible();
  await expect(page.getByText('Mesa 03 · livre', { exact: true })).toBeVisible();
  await expect(page.getByText('Alçada gerencial: visão completa do salão no mesmo escopo.', {
    exact: true,
  })).toBeVisible();

  await expect(page.getByRole('button', { name: /Confirmar pagamento/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Fechar comanda/i })).toHaveCount(0);
});
