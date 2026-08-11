import { expect, test } from '@playwright/test';
import { waitForAppReady } from './fixtures/ui';

test('controles visíveis da área da aplicação possuem nome acessível', async ({ page }) => {
  await waitForAppReady(page);
  const app = page.locator('[data-testid="stAppViewContainer"]').first();
  await expect(app).toBeVisible();

  const semNome = await app
    .locator('button:visible, input:visible, textarea:visible, select:visible')
    .evaluateAll(elements =>
      elements
        .filter(element => {
          const ariaLabel = element.getAttribute('aria-label')?.trim();
          const ariaLabelledBy = element.getAttribute('aria-labelledby')?.trim();
          const title = element.getAttribute('title')?.trim();
          if (ariaLabel || ariaLabelledBy || title) return false;

          if (element instanceof HTMLButtonElement) {
            return !element.innerText.trim() && !element.textContent?.trim();
          }
          if (
            element instanceof HTMLInputElement ||
            element instanceof HTMLTextAreaElement ||
            element instanceof HTMLSelectElement
          ) {
            const id = element.id;
            const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
            const placeholder = element.getAttribute('placeholder')?.trim();
            return !label?.textContent?.trim() && !placeholder;
          }
          return false;
        })
        .map(element => element.outerHTML.slice(0, 180)),
    );

  expect(semNome).toEqual([]);
});

test('jornada principal oferece foco por teclado sem erro de aplicação', async ({ page }) => {
  await waitForAppReady(page);
  for (let i = 0; i < 8; i += 1) {
    await page.keyboard.press('Tab');
  }
  const ativo = await page.evaluate(() => document.activeElement?.tagName ?? 'NONE');
  expect(ativo).not.toBe('BODY');
  expect(ativo).not.toBe('NONE');
  await expect(page.locator('body')).not.toContainText('Traceback');
});
