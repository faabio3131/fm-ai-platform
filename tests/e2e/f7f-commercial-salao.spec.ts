import { expect, test, type Page } from '@playwright/test';

const EMAIL = 'gerente-f7f@fm.ai';
const PASSWORD = 'F7F-Gerente-2026!';

async function waitStable(page: Page) {
  await expect(page.locator('[data-testid="stApp"]')).toHaveCount(1, { timeout: 60_000 });
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 60_000 });
  await expect(page.locator('[data-testid="stException"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
}

async function login(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await waitStable(page);
  await page.getByRole('textbox', { name: 'E-mail' }).fill(EMAIL);
  await page.getByLabel('Senha').fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByText(/Conectado como:/)).toBeVisible({ timeout: 30_000 });
  await waitStable(page);
}

async function openSalao(page: Page) {
  const tab = page.getByRole('tab', { name: /Mesas e Comandas/ }).first();
  await expect(tab).toBeVisible({ timeout: 30_000 });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByRole('heading', { name: /Mesa F71/ })).toBeVisible({ timeout: 30_000 });
  await waitStable(page);
}

async function clickAndReturnToSalao(page: Page, name: string | RegExp) {
  await page.getByRole('button', { name }).click();
  await waitStable(page);
  await openSalao(page);
}

test('F7-F fecha comanda no Salão comercial com Pagamento V1 em dinheiro', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'f7f-desktop', 'jornada desktop exclusiva');

  await login(page);
  await openSalao(page);

  await expect(page.getByText('Comanda GERENTE-F7F')).toBeVisible();
  await expect(page.getByText(/Status:\s*conta_solicitada/)).toBeVisible();
  await expect(page.getByText(/Total:\s*R\$ 20\.00/)).toBeVisible();

  await clickAndReturnToSalao(page, 'Definir pagamento integral');
  await expect(page.getByText(/Status:\s*fechamento_em_andamento/)).toBeVisible();

  await clickAndReturnToSalao(page, 'Criar pagamento canônico');
  await expect(page.getByText(/status pendente/i)).toBeVisible();

  await clickAndReturnToSalao(page, 'Confirmar recebimento em dinheiro');
  await expect(page.getByText(/status pago/i)).toBeVisible();

  await clickAndReturnToSalao(page, 'Projetar pagamento canônico confirmado');
  await expect(page.getByText('Saldo integralmente confirmado.')).toBeVisible();

  await page.getByRole('button', { name: 'Fechar comanda' }).click();
  await waitStable(page);
  await openSalao(page);

  await expect(page.getByText(/Status:\s*livre/)).toBeVisible();
  await expect(page.getByText('Comanda GERENTE-F7F')).toHaveCount(0);
});
