import { expect, test, type Page } from '@playwright/test';

const EMAIL = 'caixa-f6d@fm.ai';
const PASSWORD = 'F6D-Commercial-2026!';

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

async function openPDV(page: Page) {
  const tab = page.getByRole('tab', { name: /Frente de Caixa/ }).first();
  await expect(tab).toBeVisible({ timeout: 30_000 });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  await waitStable(page);
}

async function selectPayment(page: Page, option: string) {
  const box = page.getByRole('combobox', { name: /Forma de Pagamento/ }).first();
  await expect(box).toBeVisible();
  await expect(box).toBeEnabled();

  await box.focus();
  if ((await box.getAttribute('aria-expanded')) !== 'true') {
    await box.press('ArrowDown');
  }
  await expect(box).toHaveAttribute('aria-expanded', 'true', { timeout: 5_000 });

  const listbox = page.getByRole('listbox').filter({ visible: true }).last();
  await expect(listbox).toBeVisible({ timeout: 5_000 });
  const choice = listbox.getByRole('option', { name: option, exact: true });
  await expect(choice).toBeVisible({ timeout: 5_000 });
  await choice.click();

  await waitStable(page);
  await expect(
    page.getByRole('combobox', { name: /Forma de Pagamento/ }).first(),
  ).toHaveValue(option, { timeout: 20_000 });
}

async function finalize(page: Page) {
  await page
    .getByRole('button', { name: /Confirmar Pagamento.*Finalizar Venda|Finalizar Venda/ })
    .click();
}

test.beforeEach(async ({ page }) => {
  await login(page);
  await openPDV(page);
});

test('F6-D staging comercial autentica e finaliza dinheiro no canônico', async ({ page }) => {
  await selectPayment(page, 'Dinheiro Em Espécie');
  const received = page.getByRole('spinbutton', { name: /Valor recebido do cliente/ }).first();
  await expect(received).toBeVisible();
  await received.fill('100');
  await finalize(page);
  await expect(page.getByText(/processado com sucesso via Dinheiro Em Espécie/)).toBeVisible({
    timeout: 30_000,
  });
  await waitStable(page);
});

test('F6-D staging comercial finaliza cartão presencial no canônico', async ({ page }) => {
  await selectPayment(page, 'Cartão de Crédito');
  await finalize(page);
  await expect(page.getByText(/processado com sucesso via Cartão de Crédito/)).toBeVisible({
    timeout: 30_000,
  });
  await waitStable(page);
});

test('F6-D Pix sem provider homologado permanece fail-closed', async ({ page }) => {
  await selectPayment(page, 'Pix (Gerar QR Code Instantâneo)');
  await finalize(page);
  await expect(
    page.getByText(/Pix em produção exige confirmação válida do gateway antes da baixa/),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/processado com sucesso via Pix/)).toHaveCount(0);
  await waitStable(page);
});
