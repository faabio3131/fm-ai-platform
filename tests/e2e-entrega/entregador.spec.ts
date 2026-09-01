import { expect, test, type Page } from '@playwright/test';

async function abrirEntrega(page: Page, papel: string) {
  await page.goto(`/?papel=${papel}`, {
    waitUntil: 'domcontentloaded',
  });

  const readyMarker = page.locator(
    `[data-fm-ai-e2e-ready="true"][data-fm-ai-e2e-papel="${papel}"]`,
  );

  try {
    await expect
      .poll(
        async () => readyMarker.count(),
        {
          message: `Entrega E2E deve ficar pronta para ${papel}`,
          timeout: 30_000,
        },
      )
      .toBeGreaterThan(0);
  } catch {
    // Uma única recarga controlada cobre o cold start do Streamlit.
    // Nenhuma assertion funcional da jornada é removida.
    await page.reload({
      waitUntil: 'domcontentloaded',
    });

    await expect
      .poll(
        async () => readyMarker.count(),
        {
          message: `Entrega E2E deve ficar pronta após reload para ${papel}`,
          timeout: 60_000,
        },
      )
      .toBeGreaterThan(0);
  }

  await expect(
    readyMarker,
  ).toHaveCount(1, {
    timeout: 30_000,
  });

  await expect(
    page.locator('[data-testid="stSkeleton"]'),
  ).toHaveCount(0, {
    timeout: 30_000,
  });

  await expect(
    page.locator('[data-testid="stException"]'),
  ).toHaveCount(0);
}

async function abrirEntregador(page: Page) {
  await abrirEntrega(page, 'entregador');
}

test('entregador conclui custodia somente com financeiro resolvido', async ({ page }) => {
  await abrirEntregador(page);
  await expect(page.getByRole('heading', { name: 'Pedido pedido-paid' })).toBeVisible();

  await page.getByRole('button', { name: 'Confirmar coleta · pedido-paid' }).click();
  await expect(page.getByRole('button', { name: 'Sair em rota · pedido-paid' })).toBeVisible();
  await page.getByRole('button', { name: 'Sair em rota · pedido-paid' }).click();
  await expect(page.getByRole('button', { name: 'Confirmar entrega · pedido-paid' })).toBeVisible();
  await page.getByRole('button', { name: 'Confirmar entrega · pedido-paid' }).click();

  await expect(page.getByRole('button', { name: 'Confirmar entrega · pedido-paid' })).toHaveCount(0);
  await expect(page.getByText('Status: entregue', { exact: true })).toBeVisible();
});

test('entrega nao transforma aguardando_entrega em pagamento confirmado', async ({ page }) => {
  await abrirEntregador(page);
  await expect(page.getByRole('heading', { name: 'Pedido pedido-pending' })).toBeVisible();

  await page.getByRole('button', { name: 'Confirmar coleta · pedido-pending' }).click();
  await page.getByRole('button', { name: 'Sair em rota · pedido-pending' }).click();
  await page.getByRole('button', { name: 'Confirmar entrega · pedido-pending' }).click();

  await expect(page.getByText('Operação recusada: criterio_financeiro_pendente')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Confirmar entrega · pedido-pending' })).toBeVisible();
  await expect(page.getByText('Status: em_rota', { exact: true })).toBeVisible();
});
