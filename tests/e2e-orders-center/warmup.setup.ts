import { expect, test } from '@playwright/test';

test('aquece a primeira sessão Streamlit', async ({ page }) => {
  test.setTimeout(75_000);

  await page.goto('/');
  await expect(page.getByText(/Modo de teste isolado ativo/)).toBeVisible({
    timeout: 60_000,
  });
  await expect(
    page.getByRole('tab', { name: /Central de Pedidos/ }),
  ).toBeAttached();
});
