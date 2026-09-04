import { expect, test, type Page } from '@playwright/test';

import { selectComboboxOption } from './fixtures/ui';

const COZINHA_EMAIL = process.env.F8E_COZINHA_EMAIL ?? '';
const COZINHA_PASSWORD = process.env.F8E_COZINHA_PASSWORD ?? '';
const GARCOM_EMAIL = process.env.F8E_GARCOM_EMAIL ?? '';
const GARCOM_PASSWORD = process.env.F8E_GARCOM_PASSWORD ?? '';
const EXPEDICAO_EMAIL = process.env.F10E_EXPEDICAO_EMAIL ?? '';
const EXPEDICAO_PASSWORD = process.env.F10E_EXPEDICAO_PASSWORD ?? '';
const ENTREGADOR_EMAIL = process.env.F10E_ENTREGADOR_EMAIL ?? '';
const ENTREGADOR_PASSWORD = process.env.F10E_ENTREGADOR_PASSWORD ?? '';

// A evidência durável do gate é validada diretamente no PostgreSQL pelo workflow.
test.describe.configure({ mode: 'serial' });

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

async function login(page: Page, path: string, email: string, password: string) {
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await waitStable(page);
  await page.getByRole('textbox', { name: 'E-mail' }).fill(email);
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByText(/Conectado como:/)).toBeVisible({ timeout: 30_000 });
  await waitStable(page);
}

async function openKds(page: Page) {
  const tab = page.getByRole('tab', { name: /KDS por Setor/ }).first();
  await expect(tab).toBeVisible({ timeout: 30_000 });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: /KDS por Setor/ })).toBeVisible({
    timeout: 30_000,
  });
  await waitStable(page);
}

async function waitKdsStatus(page: Page, status: string) {
  await expect(
    page.getByText(new RegExp(`^Status:\\s*${status}$`)).last(),
  ).toBeVisible({ timeout: 30_000 });
}

async function clickKdsAndReturn(page: Page, button: string, status: string) {
  await page.getByRole('button', { name: button, exact: true }).click();
  await waitStable(page);
  await openKds(page);
  await waitKdsStatus(page, status);
}

async function waitEntregaStatus(page: Page, status: string) {
  await expect(
    page
      .locator('[data-testid="stMain"]')
      .getByText(new RegExp(`^Status:\\s*${status}$`))
      .last(),
  ).toBeVisible({ timeout: 30_000 });
  await waitStable(page);
}

test('COZINHA comercial conclui KDS e dispara handoff para EXPEDICAO', async ({
  page,
}) => {
  expect(COZINHA_EMAIL).not.toBe('');
  expect(COZINHA_PASSWORD).not.toBe('');
  await login(page, '/', COZINHA_EMAIL, COZINHA_PASSWORD);
  await openKds(page);

  const expander = page
    .locator('[data-testid="stExpander"]')
    .filter({ hasText: 'Pedidos aguardando roteamento' })
    .first();
  await expect(expander).toBeVisible();
  await expander.locator('summary').click();

  await expect(page.getByRole('combobox', { name: 'Item confirmado' }).first()).toHaveValue(
    /pedido-f8e.*Burger F8-E/,
  );
  await selectComboboxOption(page, 'Setor de destino', 'Cozinha F8-E');
  await page
    .getByRole('button', { name: 'Enviar item para produção', exact: true })
    .click();
  await waitStable(page);
  await openKds(page);

  await waitKdsStatus(page, 'aguardando');
  await clickKdsAndReturn(page, 'Aceitar', 'aceita');
  await clickKdsAndReturn(page, 'Iniciar', 'em_preparo');
  await clickKdsAndReturn(page, 'Marcar pronto', 'pronta');
  await expect(page.locator('body')).not.toContainText('Comando KDS recusado');
});

test('EXPEDICAO comercial conclui checklist e atribui ENTREGADOR canonico', async ({
  page,
}) => {
  expect(EXPEDICAO_EMAIL).not.toBe('');
  expect(EXPEDICAO_PASSWORD).not.toBe('');
  await login(page, '/Expedicao_Entrega', EXPEDICAO_EMAIL, EXPEDICAO_PASSWORD);
  await expect(page.getByRole('heading', { name: 'Expedição e Entrega' })).toBeVisible();
  await expect(page.getByText('Pedido pedido-f8e', { exact: true })).toBeVisible();
  await waitEntregaStatus(page, 'aguardando_expedicao');

  for (const label of [
    'Itens conferidos · pedido-f8e',
    'Embalagem conferida · pedido-f8e',
    'Identificação conferida · pedido-f8e',
  ]) {
    await page.getByRole('checkbox', { name: label }).check();
    await waitStable(page);
  }

  await page.getByRole('button', { name: 'Concluir checklist · pedido-f8e' }).click();
  await waitEntregaStatus(page, 'aguardando_entregador');

  const driver = page.getByRole('combobox', {
    name: 'Entregador elegível · pedido-f8e',
  });
  await expect(driver).toBeVisible({ timeout: 30_000 });
  await expect(driver).toHaveValue(`${ENTREGADOR_EMAIL} · entregador-f10e`);
  await page.getByRole('button', { name: 'Atribuir entregador · pedido-f8e' }).click();
  await waitEntregaStatus(page, 'atribuida');
  await expect(page.getByText('Entregador: entregador-f10e', { exact: true })).toBeVisible();
});

test('GARCOM autenticado nao possui alçada na superficie de Entrega', async ({ page }) => {
  expect(GARCOM_EMAIL).not.toBe('');
  expect(GARCOM_PASSWORD).not.toBe('');
  await login(page, '/Expedicao_Entrega', GARCOM_EMAIL, GARCOM_PASSWORD);
  await expect(
    page.getByText('Acesso negado: seu usuário não possui alçada de Expedição/Entrega.'),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: /Confirmar coleta|Sair em rota|Confirmar entrega/ })).toHaveCount(0);
});

test('ENTREGADOR comercial opera somente sua entrega ate conclusao', async ({ page }) => {
  expect(ENTREGADOR_EMAIL).not.toBe('');
  expect(ENTREGADOR_PASSWORD).not.toBe('');
  await login(page, '/Expedicao_Entrega', ENTREGADOR_EMAIL, ENTREGADOR_PASSWORD);
  await expect(page.getByRole('heading', { name: 'Expedição e Entrega' })).toBeVisible();
  await expect(page.getByText('Pedido pedido-f8e', { exact: true })).toBeVisible();
  await waitEntregaStatus(page, 'atribuida');

  await page.getByRole('button', { name: 'Confirmar coleta · pedido-f8e' }).click();
  await waitEntregaStatus(page, 'coletada');

  await page.getByRole('button', { name: 'Sair em rota · pedido-f8e' }).click();
  await waitEntregaStatus(page, 'em_rota');

  const proof = page.getByRole('textbox', { name: 'Referência da prova · pedido-f8e' });
  await expect(proof).toHaveValue('proof://pedido-f8e');
  await page.getByRole('button', { name: 'Confirmar entrega · pedido-f8e' }).click();
  await waitEntregaStatus(page, 'entregue');
  await expect(page.getByText('Entregador: entregador-f10e', { exact: true })).toBeVisible();
});
