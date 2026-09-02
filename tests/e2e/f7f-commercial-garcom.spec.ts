import { expect, test, type Page } from '@playwright/test';

const EMAIL = 'garcom-f7f@fm.ai';
const PASSWORD = 'F7F-Garcom-2026!';

async function waitStable(page: Page) {
  await expect(page.locator('[data-testid="stApp"]')).toHaveCount(1, { timeout: 60_000 });
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 60_000 });
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
}

async function loginGarcom(page: Page) {
  await page.goto('/Atendimento_Garcom', { waitUntil: 'domcontentloaded' });
  await waitStable(page);
  await page.getByRole('textbox', { name: 'E-mail' }).fill(EMAIL);
  await page.getByLabel('Senha').fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByText(/Conectado como:/)).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('heading', { name: 'Atendimento do Garçom' })).toBeVisible({
    timeout: 30_000,
  });
  await waitStable(page);
}

test('F7-F Garçom comercial mobile/tablet vê somente própria comanda e alerta KDS', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'f7f-desktop', 'jornada de dispositivo exclusiva');

  await loginGarcom(page);

  await expect(page.getByText(/Perfil ativo:\s*garcom/i)).toBeVisible();
  await expect(page.getByText(/Pedido pedido-f7f-garcom pronto/)).toBeVisible();
  await expect(page.getByText(/Mesa G72/)).toBeVisible();
  await expect(page.getByText(/Comanda GARCOM-F7F/)).toBeVisible();
  await expect(page.getByText(/Cozinha F7-F/)).toBeVisible();

  await expect(page.getByText('GERENTE-F7F')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Confirmar recebimento|Confirmar cartão|Fechar comanda/ })).toHaveCount(0);
  await expect(page.getByText(/Alçada do garçom: somente comandas sob sua responsabilidade/)).toBeVisible();

  const buttons = page.locator('button:visible');
  const count = await buttons.count();
  for (let i = 0; i < count; i += 1) {
    const box = await buttons.nth(i).boundingBox();
    if (box) expect(box.height).toBeGreaterThanOrEqual(44);
  }
});
