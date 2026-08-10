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
  const pendente = page.getByText('Press Enter to apply', { exact: true });

  await campo.fill(valor);
  await expect(pendente).toBeVisible();

  // fill() mantem o textbox focado. Usar o teclado da pagina evita prender
  // a acao ao elemento que o Streamlit substitui durante o rerun.
  await page.keyboard.press('Enter');

  // Pos-condicao real: o Streamlit aceitou o valor e encerrou o estado pendente.
  await expect(pendente).toHaveCount(0, { timeout: 15_000 });
}

async function aguardarPedido(page, pedidoId) {
  await expect(
    page.getByRole('heading', { name: `Pedido ${pedidoId}`, exact: true }),
  ).toBeVisible({ timeout: 15_000 });
}

test('AUTHORITATIVE_CANARY PR8 mostra pedido e cadeia financeira unica', async ({ page }) => {
  await abrirCentral(page);

  // Cada Enter provoca um rerun do Streamlit. Espere uma pós-condição observável
  // antes de aplicar o próximo filtro para não disputar com a sessão anterior.
  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'pedido-canary-pr8');
  await aguardarPedido(page, 'pedido-canary-pr8');

  await preencherEAplicar(page, 'Status', 'rascunho');
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
  await aguardarPedido(page, 'pedido-shadow-pr8');
  await expect(page.getByText('Pagamento: ausente')).toBeVisible();
  await expect(page.getByText('VendaFinanceira: ausente')).toBeVisible();
  await expect(page.getByText('Venda legada vinculada: ausente')).toBeVisible();

  await preencherEAplicar(page, 'Buscar pedido ou cliente', 'legacy-puro-sem-pedido');
  await expect(page.getByText('Nenhum pedido encontrado.')).toBeVisible({
    timeout: 15_000,
  });
});
