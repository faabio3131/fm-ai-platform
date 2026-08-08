import { expect, test } from '@playwright/test';

async function abrirCentral(page) {
  await page.goto('/');

  const tablist = page.getByRole('tablist');
  const central = tablist.getByRole('tab', { name: /Central de Pedidos/ });
  const scrollRight = page.getByRole('button', {
    name: 'Scroll tabs right',
    exact: true,
  });

  await expect(tablist).toBeVisible();
  if (await scrollRight.isVisible()) {
    await scrollRight.click();
  }
  await central.scrollIntoViewIfNeeded();
  await expect(central).toBeVisible();
  await central.click();
  await expect(page.getByRole('heading', { name: /Central de Pedidos/ })).toBeVisible();
}

async function preencherEAplicar(page, nome, valor) {
  const campo = page.getByRole('textbox', { name: nome, exact: true });
  await campo.fill(valor);
  await campo.press('Enter');
}

test('AUTHORITATIVE_CANARY PR8 mostra pedido e cadeia financeira unica', async ({ page }) => {
  await abrirCentral(page);
  await preencherEAplicar(page, 'Status', 'rascunho');
  await preencherEAplicar(page, 'Canal', 'presencial');
  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'pedido-canary-pr8');
  await expect(
    page.getByRole('heading', { name: 'Pedido pedido-canary-pr8', exact: true }),
  ).toBeVisible();
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
  await expect(page.getByText(/Comando negado por RBAC: permissao_insuficiente; auditoria=1/)).toBeVisible();
  await page.getByRole('button', { name: 'Demonstrar versão desatualizada' }).click();
  await expect(page.getByText(/Optimistic locking: pedido_concorrente/)).toBeVisible();
  await page.getByRole('button', { name: 'Enviar para confirmação' }).click();
  await expect(page.getByText(/Comando permitido; evento e auditoria registrados \(1\)/)).toBeVisible();
});

test('SHADOW nao inventa financeiro e Venda LEGACY pura nao cria Pedido', async ({ page }) => {
  await abrirCentral(page);
  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'pedido-shadow-pr8');
  await expect(
    page.getByRole('heading', { name: 'Pedido pedido-shadow-pr8', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Pagamento: ausente')).toBeVisible();
  await expect(page.getByText('VendaFinanceira: ausente')).toBeVisible();
  await expect(page.getByText('Venda legada vinculada: ausente')).toBeVisible();

  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'legacy-puro-sem-pedido');
  await expect(page.getByText('Nenhum pedido encontrado.')).toBeVisible();
});
