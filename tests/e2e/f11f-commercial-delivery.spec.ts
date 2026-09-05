import { execFileSync } from 'node:child_process';
import { expect, type Locator, type Page, test } from '@playwright/test';

const GERENTE_EMAIL = process.env.F11F_GERENTE_EMAIL ?? '';
const GERENTE_PASSWORD = process.env.F11F_GERENTE_PASSWORD ?? '';
const GARCOM_EMAIL = process.env.F11F_GARCOM_EMAIL ?? '';
const GARCOM_PASSWORD = process.env.F11F_GARCOM_PASSWORD ?? '';
const OTHER_GERENTE_EMAIL = process.env.F11F_OTHER_GERENTE_EMAIL ?? '';
const OTHER_GERENTE_PASSWORD = process.env.F11F_OTHER_GERENTE_PASSWORD ?? '';

async function waitStable(page: Page) {
  await expect(page.locator('[data-testid="stApp"]')).toHaveCount(1, { timeout: 60_000 });
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 60_000 });
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
}

async function login(page: Page, email: string, password: string) {
  expect(email).not.toBe('');
  expect(password).not.toBe('');
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await waitStable(page);
  await page.getByRole('textbox', { name: 'E-mail' }).fill(email);
  await page.getByLabel('Senha').fill(password);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByText(/Conectado como:/)).toBeVisible({ timeout: 30_000 });
  await waitStable(page);
}

async function openDelivery(page: Page) {
  const tab = page.getByRole('tab', { name: /Delivery Próprio/ }).first();
  await expect(tab).toBeVisible({ timeout: 30_000 });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: /Delivery Próprio/ })).toBeVisible({ timeout: 30_000 });
  await waitStable(page);
}

async function selecionarCombo(combo: Locator, opcao: string) {
  await expect(combo).toBeVisible();
  await expect(combo).toBeEnabled();
  if ((await combo.inputValue()) === opcao) return;
  await expect(async () => {
    await combo.focus();
    await combo.press('ArrowDown');
    await expect(combo).toHaveAttribute('aria-expanded', 'true', { timeout: 5_000 });
  }).toPass({ timeout: 15_000 });
  const listbox = combo.page().getByRole('listbox').filter({ visible: true }).last();
  await expect(listbox).toBeVisible({ timeout: 5_000 });
  await listbox.getByRole('option', { name: opcao, exact: true }).click();
  await expect(combo).toHaveValue(opcao, { timeout: 15_000 });
}

async function selecionarCliente(page: Page, clienteId: string) {
  const combo = page.getByRole('combobox', { name: /Cliente CRM/ }).filter({ visible: true }).first();
  await selecionarCombo(combo, clienteId);
  await waitStable(page);
  await openDelivery(page);
  await expect(page.getByText(/Endereço validado:/)).toBeVisible();
}

async function iniciarCarrinho(page: Page) {
  await page.getByRole('button', { name: /Iniciar novo pedido/ }).click();
  await waitStable(page);
  await openDelivery(page);
  await expect(page.getByRole('heading', { name: /1\. Cardápio/ })).toBeVisible();
  await expect(page.getByText('Burger Delivery F11-F', { exact: true }).first()).toBeVisible();
}

async function adicionarProduto(page: Page) {
  await page.getByRole('button', { name: 'Adicionar', exact: true }).click();
  await waitStable(page);
  await openDelivery(page);
  await expect(page.getByText(/1x Burger Delivery F11-F/)).toBeVisible();
}

async function cotar(page: Page) {
  await page.getByRole('button', { name: /Calcular taxa e SLA no endereço validado/ }).click();
  await waitStable(page);
  await openDelivery(page);
}

function anexarBeneficioResolvido() {
  const python = process.env.PYTHON ?? 'python';
  execFileSync(python, ['-m', 'scripts.prepare_f11f_resolved_benefit'], {
    env: process.env,
    stdio: 'inherit',
  });
}

test('F11-F executa Delivery comercial no app.py e reconcilia cancelamento no PostgreSQL', async ({ page }) => {
  await login(page, GERENTE_EMAIL, GERENTE_PASSWORD);
  await openDelivery(page);
  await expect(page.getByText(/Escopo ativo: tenant-f11f-a \/ unidade-f11f-a/)).toBeVisible();
  await selecionarCliente(page, 'cliente-f11f-a');
  await iniciarCarrinho(page);
  await adicionarProduto(page);
  await cotar(page);
  await expect(page.getByText(/Centro F11-F: taxa R\$ 7\.00/)).toBeVisible();

  anexarBeneficioResolvido();
  const pagamento = page.getByRole('combobox', { name: /Forma de pagamento/ }).filter({ visible: true }).first();
  await selecionarCombo(pagamento, 'Pagamento na entrega');
  await waitStable(page);
  await openDelivery(page);
  await expect(page.getByText(/Cupom reservado: R\$ 5\.00/)).toBeVisible();
  await expect(page.getByText(/Total estimado/)).toBeVisible();
  await expect(page.getByText('R$ 34.00', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: /Confirmar pedido/ }).click();
  await waitStable(page);
  await openDelivery(page);
  await expect(page.getByRole('heading', { name: /4\. Acompanhamento/ })).toBeVisible();
  await expect(page.getByText(/Pedido: aguardando_confirmacao/)).toBeVisible();
  await expect(page.getByText(/Entrega: aguardando_producao/)).toBeVisible();
  await expect(page.getByText(/Total canônico/)).toBeVisible();
  await expect(page.getByText('R$ 34.00', { exact: true })).toBeVisible();

  await page.getByText('Cancelar pedido', { exact: true }).click();
  await page.getByLabel('Motivo').fill('Solicitacao comercial F11-F');
  await page.getByRole('button', { name: /Cancelar no fluxo canônico/ }).click();
  await waitStable(page);
  await openDelivery(page);
  await expect(page.getByText(/Pedido: cancelado/)).toBeVisible();
  await expect(page.getByText(/Entrega: cancelada/)).toBeVisible();
});

test('F11-F falha fechado para endereço validado fora da área sem criar Pedido', async ({ page }) => {
  await login(page, GERENTE_EMAIL, GERENTE_PASSWORD);
  await openDelivery(page);
  await selecionarCliente(page, 'cliente-f11f-out');
  await expect(page.getByText(/CEP 99999999/)).toBeVisible();
  await iniciarCarrinho(page);
  await adicionarProduto(page);
  await cotar(page);
  await expect(page.getByText(/fora_da_area_de_entrega/)).toBeVisible();
  await expect(page.getByRole('heading', { name: /4\. Acompanhamento/ })).toHaveCount(0);
});

test('F11-F nega superfície Delivery ao GARCOM sem cliente.visualizar', async ({ page }) => {
  await login(page, GARCOM_EMAIL, GARCOM_PASSWORD);
  await expect(page.getByRole('tab', { name: /Delivery Próprio/ })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: /Delivery Próprio/ })).toHaveCount(0);
});

test('F11-F recusa identidade de outro tenant no runtime configurado para tenant A', async ({ page }) => {
  expect(OTHER_GERENTE_EMAIL).not.toBe('');
  expect(OTHER_GERENTE_PASSWORD).not.toBe('');
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await waitStable(page);
  await page.getByRole('textbox', { name: 'E-mail' }).fill(OTHER_GERENTE_EMAIL);
  await page.getByLabel('Senha').fill(OTHER_GERENTE_PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(
    page.getByText(/E-mail ou senha inválidos, ou usuário sem acesso a esta unidade/),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Conectado como:/)).toHaveCount(0);
  await expect(page.getByRole('tab', { name: /Delivery Próprio/ })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('cliente-f11f-a');
});
