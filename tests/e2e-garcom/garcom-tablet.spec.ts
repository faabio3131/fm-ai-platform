import { expect, test, type Page } from '@playwright/test';

async function abrirGarcomTablet(page: Page) {
  await page.goto('/?papel=garcom', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Garcom E2E pronto', { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole('heading', { name: 'Atendimento do Garçom' })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveCount(1, {
    timeout: 30_000,
  });
  await expect(page.locator('[data-fm-ai-e2e-papel="garcom"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, {
    timeout: 30_000,
  });
}

test('garcom no tablet preserva alçada, alertas e separação financeira', async ({ page }) => {
  await abrirGarcomTablet(page);

  expect(page.viewportSize()).toEqual({ width: 820, height: 1180 });
  await expect(page.getByText('Perfil ativo: garcom', { exact: false })).toBeVisible();

  await expect(page.getByText('Pedido pedido-garcom-1 pronto', { exact: false })).toBeVisible();
  await expect(page.getByText('pedido-garcom-2 pronto', { exact: false })).toHaveCount(0);

  await expect(page.getByText('Mesa 01 · ocupada', { exact: true })).toBeVisible();
  await expect(page.getByText('Mesa 03 · livre', { exact: true })).toBeVisible();
  await expect(page.getByText('Mesa 02 · ocupada', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Comanda C-001', { exact: true })).toBeVisible();
  await expect(page.getByText('Comanda C-002', { exact: true })).toHaveCount(0);

  await expect(
    page.getByText(/Alçada do garçom: somente comandas sob sua responsabilidade/),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: /pagamento/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /fechar comanda/i })).toHaveCount(0);

  // O projeto mobile valida a mutação "Solicitar conta". O tablet permanece
  // somente leitura para não depender da ordem dos projetos sobre o mesmo seed.
  await expect(page.getByRole('button', { name: /pagamento/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /fechar comanda/i })).toHaveCount(0);
});
