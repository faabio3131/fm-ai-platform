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
    // O cold start do Streamlit pode aceitar HTTP antes de concluir
    // a sessão WebSocket/renderização. Uma única recarga controlada
    // é permitida; as pós-condições funcionais permanecem obrigatórias.
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

async function marcarCheckbox(page: Page, nome: string) {
  const readyMarker = page.locator(
    '[data-fm-ai-e2e-ready="true"][data-fm-ai-e2e-papel="expedicao"]',
  );

  // O baseline precisa pertencer a uma única sessão Streamlit estável.
  await expect(
    readyMarker,
  ).toHaveCount(1, {
    timeout: 30_000,
  });

  const rawRunAnterior = await readyMarker.getAttribute(
    'data-fm-ai-e2e-run',
  );

  const execucaoAnterior = Number(rawRunAnterior);

  if (!Number.isFinite(execucaoAnterior)) {
    throw new Error(
      `Run E2E inválido antes do checkbox ${nome}: ${rawRunAnterior}`,
    );
  }

  const checkbox = page.getByRole(
    'checkbox',
    {
      name: nome,
    },
  );

  await expect(checkbox).toBeVisible();
  await expect(checkbox).toBeEnabled();

  await checkbox.evaluate(
    (elemento: HTMLInputElement) => {
      if (!elemento.checked) {
        elemento.click();
      }
    },
  );

  // Durante um rerun o Streamlit pode manter mais de um marker
  // temporariamente. A referência anterior, porém, veio de uma
  // sessão estabilizada em exatamente um marker.
  await expect
    .poll(
      async () => {
        const runs = await page
          .locator(
            '[data-fm-ai-e2e-ready="true"][data-fm-ai-e2e-papel="expedicao"]',
          )
          .evaluateAll(elements =>
            elements
              .map(element =>
                Number(
                  element.getAttribute(
                    'data-fm-ai-e2e-run',
                  ),
                ),
              )
              .filter(value =>
                Number.isFinite(value),
              ),
          );

        if (!runs.length) {
          return -1;
        }

        return Math.max(...runs);
      },
      {
        message:
          `Streamlit deve concluir o rerun após checkbox ${nome}`,
        timeout: 30_000,
      },
    )
    .toBeGreaterThan(execucaoAnterior);

  // O rerun precisa terminar sem deixar markers concorrentes.
  await expect(
    readyMarker,
  ).toHaveCount(1, {
    timeout: 30_000,
  });

  await expect(
    page.getByRole(
      'checkbox',
      {
        name: nome,
      },
    ),
  ).toBeChecked({
    timeout: 15_000,
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

test('expedicao conclui checklist e atribui entregador sem acessar financeiro', async ({ page }) => {
  await abrirEntrega(page, 'expedicao');
  await expect(page.getByRole('heading', { name: 'Expedição e Entrega' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Pedido pedido-exp' })).toBeVisible();

  await marcarCheckbox(page, 'Itens conferidos · pedido-exp');
  await marcarCheckbox(page, 'Embalagem conferida · pedido-exp');
  await marcarCheckbox(page, 'Identificação conferida · pedido-exp');
  await page.getByRole('button', { name: 'Concluir checklist · pedido-exp' }).click();

  await expect(page.getByRole('button', { name: 'Concluir checklist · pedido-exp' })).toHaveCount(0);
  await expect(page.getByText('Status: aguardando_entregador', { exact: true })).toBeVisible();

  await page.getByRole('textbox', { name: 'ID do entregador · pedido-exp' }).fill('driver-2');
  await page.getByRole('button', { name: 'Atribuir entregador · pedido-exp' }).click();

  await expect(page.getByRole('button', { name: 'Atribuir entregador · pedido-exp' })).toHaveCount(0);
  await expect(page.getByText('Entregador: driver-2', { exact: true })).toBeVisible();
});
