import { expect, type Page } from '@playwright/test';

export async function waitForAppReady(page: Page) {
  await page.goto('/', { waitUntil: 'networkidle' });
  await expect(page).toHaveTitle(/.+/);
  await expect(page.getByText(/Painel de Gestão|Modo de teste isolado ativo|F&M AI FOOD/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, { timeout: 30_000 });
}

export async function openTab(page: Page, name: string | RegExp) {
  const pattern = typeof name === 'string' ? new RegExp(name) : name;
  const roleTab = page.getByRole('tab', { name: pattern }).first();
  if (await roleTab.count()) {
    await roleTab.click();
  } else {
    const textTab = page.getByText(pattern).first();
    if (!(await textTab.count())) {
      const candidates = await page.locator('button, [role="tab"], [data-testid="stTab"]').allTextContents();
      throw new Error(`Aba não encontrada: ${pattern}. Candidatas: ${candidates.join(' | ')}`);
    }
    await textTab.click();
  }
  await expect(page.locator('body')).toContainText(pattern, { timeout: 15_000 });
}

export async function expectNoFatal(page: Page) {
  await expect(page.locator('body')).not.toContainText('Traceback');
  await expect(page.locator('body')).not.toContainText('GEMINI_API_KEY');
}

export async function fillNumber(page: Page, label: string | RegExp, value: string) {
  const input = page.getByLabel(label).first();
  await input.fill(value);
}
