import { expect, test } from '@playwright/test';

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
  await campo.fill(valor);
  await campo.press('Enter');
  await expect(campo).toHaveValue(valor);
}

test('AUTHORITATIVE_CANARY PR8 mostra pedido e cadeia financeira unica', async ({ page }) => {
  await abrirCentral(page);
  await preencherEAplicar(page, 'Status', 'rascunho');
  await preencherEAplicar(page, 'Canal', 'presencial');
  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'pedido-canary-pr8');
  await expect(
    page.getByRole('heading', { name: 'Pedido pedido-canary-pr8', exact: true }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Burger Canary PR8')).toBeVisible();
  await expect(page.getByText(/Queijo extra/)).toBeVisible();
  await expect(page.getByText(/Total:\s*R\$ 24\.00/)).toBeVisible();
  await expect(page.getByText(/pedido.criado/)).toBeVisible();
  await expect(page.getByText('confirmado', { exact: true })).toBeVisible();
  await expect(page.getByText(/Pagamento: pagamento-canary/)).toBeVisible();
  await expect(page.getByText(/VendaFinanceira: venda-financeira-canary/)).toBeVisible();
  await expect(page.getByText(/Venda legada vinculada: 1/)).toHaveCount(1);
  await expect(page.getByText(/Reconciliação: reconciliacao-canary/)).toBeVisible();

  await page.getByRole('button', { name: 'Demonstrar ação negada' }).click();
  await expect(
    page.getByText(/Comando negado por RBAC: permissao_insuficiente; auditoria=1/),
  ).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: 'Demonstrar versão desatualizada' }).click();
  await expect(page.getByText(/Optimistic locking: pedido_concorrente/)).toBeVisible({
    timeout: 15_000,
  });
  await page.getByRole('button', { name: 'Enviar para confirmação' }).click();
  await expect(
    page.getByText(/Comando permitido; evento e auditoria registrados \(1\)/),
  ).toBeVisible({ timeout: 15_000 });
});

test('SHADOW nao inventa financeiro e Venda LEGACY pura nao cria Pedido', async ({ page }) => {
  await abrirCentral(page);
  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'pedido-shadow-pr8');
  await expect(
    page.getByRole('heading', { name: 'Pedido pedido-shadow-pr8', exact: true }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Pagamento: ausente')).toBeVisible();
  await expect(page.getByText('VendaFinanceira: ausente')).toBeVisible();
  await expect(page.getByText('Venda legada vinculada: ausente')).toBeVisible();

  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'legacy-puro-sem-pedido');
  await expect(page.getByText('Nenhum pedido encontrado.')).toBeVisible({
    timeout: 15_000,
  });
});
