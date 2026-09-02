import { expect, test, type Page } from '@playwright/test';

import { selectComboboxOption } from './fixtures/ui';

const COZINHA_EMAIL = process.env.F8E_COZINHA_EMAIL ?? '';
const COZINHA_PASSWORD = process.env.F8E_COZINHA_PASSWORD ?? '';
const GARCOM_EMAIL = process.env.F8E_GARCOM_EMAIL ?? '';
const GARCOM_PASSWORD = process.env.F8E_GARCOM_PASSWORD ?? '';

async function waitStable(page: Page) {
  await expect(page.locator('[data-testid="stApp"]')).toHaveCount(1, {
    timeout: 60_000,
  });
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, {
    timeout: 60_000,
  });
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
}

async function login(page: Page, email: string, password: string) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await waitStable(page);
  await page.getByRole('textbox', { name: 'E-mail' }).fill(email);
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByText(/Conectado como:/)).toBeVisible({
    timeout: 30_000,
  });
  await waitStable(page);
}

async function openKds(page: Page) {
  const tab = page.getByRole('tab', { name: /KDS por Setor/ }).first();
  await expect(tab).toBeVisible({ timeout: 30_000 });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  await expect(
    page.getByRole('heading', { name: /KDS por Setor/ }),
  ).toBeVisible({ timeout: 30_000 });
  await waitStable(page);
}

async function waitStatus(page: Page, status: string) {
  await expect(
    page.getByText(new RegExp(`^Status:\\s*${status}$`)).last(),
  ).toBeVisible({ timeout: 30_000 });
}

async function clickAndReturnToKds(
  page: Page,
  button: string,
  status: string,
) {
  await page.getByRole('button', { name: button, exact: true }).click();
  await waitStable(page);
  await openKds(page);
  await waitStatus(page, status);
}

test('GARCOM autenticado nao recebe superficie KDS comercial', async ({ page }) => {
  expect(GARCOM_EMAIL).not.toBe('');
  expect(GARCOM_PASSWORD).not.toBe('');
  await login(page, GARCOM_EMAIL, GARCOM_PASSWORD);
  await expect(page.getByRole('tab', { name: /KDS por Setor/ })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('KDS por Setor');
});

test('COZINHA roteia Pedido real e conclui producao no app comercial', async ({
  page,
}) => {
  expect(COZINHA_EMAIL).not.toBe('');
  expect(COZINHA_PASSWORD).not.toBe('');
  await login(page, COZINHA_EMAIL, COZINHA_PASSWORD);
  await openKds(page);

  const expander = page
    .locator('[data-testid="stExpander"]')
    .filter({ hasText: 'Pedidos aguardando roteamento' })
    .first();
  await expect(expander).toBeVisible();
  await expander.locator('summary').click();

  const itemConfirmado = page
    .getByRole('combobox', { name: 'Item confirmado' })
    .first();
  await expect(itemConfirmado).toBeVisible({ timeout: 15_000 });
  await expect(itemConfirmado).toHaveValue(/pedido-f8e.*Burger F8-E/);

  await selectComboboxOption(page, 'Setor de destino', 'Cozinha F8-E');

  await page
    .getByRole('button', { name: 'Enviar item para produção', exact: true })
    .click();
  await waitStable(page);
  await openKds(page);

  await waitStatus(page, 'aguardando');
  await clickAndReturnToKds(page, 'Aceitar', 'aceita');
  await clickAndReturnToKds(page, 'Iniciar', 'em_preparo');
  await clickAndReturnToKds(page, 'Marcar pronto', 'pronta');

  await expect(
    page.getByRole('button', { name: 'Registrar retirada', exact: true }),
  ).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Comando KDS recusado');
});
