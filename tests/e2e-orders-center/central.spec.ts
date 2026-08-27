import { expect, test } from '@playwright/test';

import { clickAndWaitForStreamlitRerun } from '../e2e/fixtures/ui';

async function abrirCentral(page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Central E2E pronta', { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole('heading', { name: /Central de Pedidos/ })).toBeVisible({
    timeout: 10_000,
  });
}

async function preencherEAplicar(page, nome, valor) {
  const campo = page.getByRole('textbox', { name: nome, exact: true });
  const pendente = page.getByText('Press Enter to apply', { exact: true });

  await campo.fill(valor);
  await expect(pendente).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(pendente).toHaveCount(0, { timeout: 15_000 });
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
  await expect(page.getByText(/aguardando_confirmacao/).first()).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole('button', { name: 'Enviar para confirmação' })).toHaveCount(0);
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
