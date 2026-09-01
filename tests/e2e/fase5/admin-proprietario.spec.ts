import { expect, test } from '@playwright/test';

async function login(page, email: string, password: string) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: /Acesso ao Gerente AI/ })).toBeVisible();
  await page.getByRole('textbox', { name: 'E-mail' }).fill(email);
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Entrar' }).click();
}

test('proprietario administra empresa com PIN e perfil operacional falha fechado', async ({ page }) => {
  const jsErrors: string[] = [];
  page.on('pageerror', error => jsErrors.push(error.message));

  await login(page, 'owner.f5.e2e@example.test', 'senha-owner-f5-e2e-123');

  await expect(
    page.getByText(/Área protegida. Informe seu PIN administrativo individual/),
  ).toBeVisible();
  await page.getByLabel('PIN administrativo').fill('472839');
  await page.getByRole('button', { name: /Desbloquear área administrativa/ }).click();

  await expect(page.getByRole('heading', { name: /Administração \/ Proprietário/ })).toBeVisible();
  await expect(page.getByText('Centro Administrativo', { exact: true })).toBeVisible();

  const empresaTab = page.getByRole('tab', { name: /Empresa e unidades/ });
  await empresaTab.click();
  await expect(empresaTab).toHaveAttribute('aria-selected', 'true');

  await expect(page.getByRole('textbox', { name: 'Nome da empresa' })).toHaveValue(
    'Empresa F5 E2E',
  );
  await page.getByRole('textbox', { name: 'Nome da empresa' }).fill('Empresa F5 Atualizada');
  await page.getByLabel('PIN administrativo para salvar empresa').fill('472839');
  await page.getByRole('button', { name: 'Salvar empresa' }).click();

  await empresaTab.click();
  await expect(page.getByRole('textbox', { name: 'Nome da empresa' })).toHaveValue(
    'Empresa F5 Atualizada',
  );
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');

  await page.getByRole('button', { name: 'Sair' }).click();
  await login(page, 'caixa.f5.e2e@example.test', 'senha-caixa-f5-e2e-456');

  await expect(
    page.getByText(/Área restrita: seu usuário não possui autorização/),
  ).toBeVisible();
  await expect(page.getByText('Centro Administrativo', { exact: true })).toHaveCount(0);
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  expect(jsErrors).toEqual([]);
});
