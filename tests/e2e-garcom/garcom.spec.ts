import { expect, test, type Page } from '@playwright/test';

async function abrirGarcom(page: Page) {
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

test('garcom no celular vê somente sua alçada e recebe aviso de pronto', async ({ page }) => {
  await abrirGarcom(page);

  expect(page.viewportSize()).toEqual({ width: 390, height: 844 });
  await expect(page.getByText('Perfil ativo: garcom', { exact: false })).toBeVisible();
  await expect(page.getByText('Pedido pedido-garcom-1 pronto', { exact: false })).toBeVisible();
  await expect(page.getByText('pedido-garcom-2 pronto', { exact: false })).toHaveCount(0);

  await expect(page.getByText('Mesa 01 · ocupada', { exact: true })).toBeVisible();
  await expect(page.getByText('Mesa 03 · livre', { exact: true })).toBeVisible();
  await expect(page.getByText('Mesa 02 · ocupada', { exact: true })).toHaveCount(0);
  await expect(page.getByText('Comanda sob sua responsabilidade.', { exact: true })).toBeVisible();
  await expect(
    page.getByText(/Alçada do garçom: somente comandas sob sua responsabilidade/),
  ).toBeVisible();

  const solicitar = page.getByRole('button', { name: 'Solicitar conta', exact: true });
  await expect(solicitar).toBeVisible();
  const box = await solicitar.boundingBox();
  expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);

  await solicitar.click();
  await expect(page.getByText('Status: conta_solicitada', { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText('Pagamento e fechamento exigem alçada financeira/gerencial.', {
      exact: true,
    }),
  ).toBeVisible();
});
