import { expect, test, type Page } from '@playwright/test';

import { selectComboboxOption } from './fixtures/ui';

const COZINHA_EMAIL = process.env.F8E_COZINHA_EMAIL ?? '';
const COZINHA_PASSWORD = process.env.F8E_COZINHA_PASSWORD ?? '';
const GARCOM_EMAIL = process.env.F8E_GARCOM_EMAIL ?? '';
const GARCOM_PASSWORD = process.env.F8E_GARCOM_PASSWORD ?? '';

async function waitStable(page: Page) {
  await expect(page.locator('[data-testid="stApp"]')).toHaveCount(1, { timeout: 60_000 });
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 60_000 });
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
}

async function login(page: Page, email: string, password: string) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await waitStable(page);
  await page.getByRole('textbox', { name: 'E-mail' }).fill(email);
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByText(/Conectado como:/)).toBeVisible({ timeout: 30_000 });
  await waitStable(page);
}

async function openTab(page: Page, name: RegExp) {
  const tab = page.getByRole('tab', { name }).first();
  await expect(tab).toBeVisible({ timeout: 30_000 });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  await waitStable(page);
}

function visibleTabPanel(page: Page) {
  return page.locator('[role="tabpanel"]:visible').first();
}

test.describe.configure({ mode: 'serial' });

test('COZINHA roteia Pedido real, cria spool e imprime via RAW TCP comercial', async ({ page }) => {
  expect(COZINHA_EMAIL).not.toBe('');
  expect(COZINHA_PASSWORD).not.toBe('');
  await login(page, COZINHA_EMAIL, COZINHA_PASSWORD);
  await openTab(page, /KDS por Setor/);

  const expander = page
    .locator('[data-testid="stExpander"]')
    .filter({ hasText: 'Pedidos aguardando roteamento' })
    .first();
  await expander.locator('summary').click();
  await expect(page.getByRole('combobox', { name: 'Item confirmado' }).first()).toHaveValue(
    /pedido-f8e.*Burger F8-E/,
  );
  await selectComboboxOption(page, 'Setor de destino', 'Cozinha F8-E');
  await page.getByRole('button', { name: 'Enviar item para produção', exact: true }).click();
  await waitStable(page);

  await openTab(page, /Impressão Operacional/);
  let printPanel = visibleTabPanel(page);
  await expect(printPanel).toContainText('pedido-f8e', { timeout: 30_000 });
  await expect(printPanel).toContainText(/pendente/);
  await page.getByRole('button', { name: 'Processar impressão', exact: true }).click();
  await waitStable(page);
  await openTab(page, /Impressão Operacional/);
  printPanel = visibleTabPanel(page);
  await expect(printPanel).toContainText(/impresso/, { timeout: 30_000 });

  await page.getByRole('textbox', { name: 'Motivo da reimpressão' }).fill('ticket danificado F9-E');
  await page.getByRole('button', { name: 'Criar reimpressão', exact: true }).click();
  await waitStable(page);
  await openTab(page, /Impressão Operacional/);
  printPanel = visibleTabPanel(page);
  await expect(printPanel).toContainText(/pendente/, { timeout: 30_000 });
});

test('GARCOM autenticado não consegue criar reimpressão', async ({ page }) => {
  expect(GARCOM_EMAIL).not.toBe('');
  expect(GARCOM_PASSWORD).not.toBe('');
  await login(page, GARCOM_EMAIL, GARCOM_PASSWORD);
  await openTab(page, /Impressão Operacional/);
  await page.getByRole('textbox', { name: 'Motivo da reimpressão' }).fill('tentativa sem alçada');
  await page.getByRole('button', { name: 'Criar reimpressão', exact: true }).click();
  await expect(page.getByText('Reimpressão não autorizada ou motivo inválido.')).toBeVisible({
    timeout: 30_000,
  });
});
