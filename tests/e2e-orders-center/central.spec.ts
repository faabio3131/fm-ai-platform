import { expect, test } from '@playwright/test';

import {
  clickAndWaitForStreamlitRerun,
  waitForAppReady,
} from '../e2e/fixtures/ui';

async function latestReadyRun(page) {
  const values = await page
    .locator('[data-fm-ai-e2e-ready="true"]')
    .evaluateAll(elements =>
      elements
        .map(element => Number(element.getAttribute('data-fm-ai-e2e-run')))
        .filter(value => Number.isFinite(value)),
    );

  if (!values.length) {
    return null;
  }

  return Math.max(...values);
}

async function abrirCentral(page) {
  await waitForAppReady(page);

  await expect(
    page.getByText('Central E2E pronta', { exact: true }),
  ).toBeVisible();

  await expect(
    page.getByRole('heading', { name: /Central de Pedidos/ }),
  ).toBeVisible();

  await expect(
    page.locator('[data-testid="stSkeleton"]'),
  ).toHaveCount(0);

  await expect(
    page.locator('[data-testid="stException"]'),
  ).toHaveCount(0);
}

async function preencherEAplicar(page, nome, valor) {
  const campo = page.getByRole('textbox', {
    name: nome,
    exact: true,
  });

  const pendente = page.getByText(
    'Press Enter to apply',
    {
      exact: true,
    },
  );

  const runBefore = await latestReadyRun(page);

  await campo.fill(valor);
  await expect(pendente).toBeVisible();

  await page.keyboard.press('Enter');

  await expect
    .poll(
      async () => {
        const runAfter = await latestReadyRun(page);

        return (
          runAfter !== null
          && (
            runBefore === null
            || runAfter > runBefore
          )
        );
      },
      {
        message:
          `Streamlit deve concluir o rerun do campo ${nome}`,
        timeout: 30_000,
      },
    )
    .toBe(true);

  await expect(
    page.locator('[data-testid="stSkeleton"]'),
  ).toHaveCount(
    0,
    {
      timeout: 30_000,
    },
  );

  await expect(
    page.locator('[data-testid="stException"]'),
  ).toHaveCount(0);

  await expect(campo).toHaveValue(valor);
}

async function aguardarPedido(page, pedidoId) {
  await expect(
    page.getByRole('heading', { name: `Pedido ${pedidoId}`, exact: true }),
  ).toBeVisible({ timeout: 15_000 });
}

test('Central usa Pedido canonico, mostra financeiro e executa transicao real', async ({ page }) => {
  await abrirCentral(page);

  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'pedido-canary-pr8');
  await aguardarPedido(page, 'pedido-canary-pr8');

  await preencherEAplicar(page, 'Canal', 'presencial');
  await aguardarPedido(page, 'pedido-canary-pr8');

  await expect(page.getByText('Burger Canary PR8')).toBeVisible();
  await expect(page.getByText(/Queijo extra/)).toBeVisible();
  await expect(page.getByText(/Total:\s*R\$ 24\.00/)).toBeVisible();
  await expect(page.getByText(/pedido.criado/)).toBeVisible();
  await expect(
    page.getByRole('paragraph').filter({ hasText: /^confirmado$/ }),
  ).toBeVisible();
  await expect(page.getByText(/Pagamento: pagamento-canary/)).toBeVisible();
  await expect(page.getByText(/Venda financeira: venda-financeira-canary/)).toBeVisible();
  await expect(page.getByText(/Reconciliação: reconciliacao-canary/)).toBeVisible();

  await clickAndWaitForStreamlitRerun(page, 'Enviar para confirmação');
  const statusAtualizado = page
    .getByRole('paragraph')
    .filter({
      hasText: /Status:\s*aguardando_confirmacao/,
    });

  await expect(statusAtualizado).toBeVisible({
    timeout: 15_000,
  });

  await expect(
    page.getByRole('button', {
      name: 'Enviar para confirmação',
    }),
  ).toHaveCount(0);
});

test('Central nao inventa financeiro e Venda LEGACY pura nao cria Pedido', async ({ page }) => {
  await abrirCentral(page);
  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'pedido-shadow-pr8');
  await aguardarPedido(page, 'pedido-shadow-pr8');
  await expect(page.getByText('Pagamento: ausente')).toBeVisible();
  await expect(page.getByText('Venda financeira: ausente')).toBeVisible();

  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'legacy-puro-sem-pedido');
  await expect(page.getByText('Nenhum pedido encontrado para os filtros atuais.')).toBeVisible({
    timeout: 15_000,
  });
});
