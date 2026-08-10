import { expect, test, type Page } from '@playwright/test';

import { selectComboboxOption } from '../e2e/fixtures/ui';

async function abrirKDS(page: Page) {
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('KDS E2E pronto', { exact: true })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByRole('heading', { name: /KDS por Setor/ })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator('[data-fm-ai-e2e-ready="true"]')).toHaveCount(1, {
    timeout: 30_000,
  });
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, {
    timeout: 30_000,
  });
}

async function aguardarProducao(page: Page, producaoId: string) {
  await expect(
    page.getByRole('heading', { name: `Produção ${producaoId}`, exact: true }),
  ).toBeVisible({ timeout: 15_000 });
}

async function aguardarStatus(page: Page, status: string) {
  await expect(
    page.getByText(new RegExp(`^Status:\\s*${status}$`)).last(),
  ).toBeVisible({ timeout: 15_000 });
}

async function clicarEAguardarStatus(page: Page, botao: string, status: string) {
  await page.getByRole('button', { name: botao, exact: true }).click();
  await aguardarStatus(page, status);
}

async function ativarOffline(page: Page) {
  const readyMarker = page.locator('[data-fm-ai-e2e-ready="true"]');
  const runBefore = await readyMarker.getAttribute('data-fm-ai-e2e-run');
  const checkbox = page.getByRole('checkbox', {
    name: 'Simular KDS offline',
    exact: true,
  });

  await expect(checkbox).toBeVisible();
  await expect(checkbox).toBeEnabled();

  // O Streamlit envolve o input em um label React e, durante rerenders,
  // overlays transitórios podem interceptar o ponteiro. `force` mantém a
  // interação no controle real; a pós-condição abaixo prova que o rerun ocorreu.
  await checkbox.check({ force: true });

  await expect
    .poll(
      async () => {
        const runAfter = await readyMarker.getAttribute('data-fm-ai-e2e-run');
        return runAfter !== null && runAfter !== runBefore;
      },
      {
        message: 'Streamlit deve concluir o rerun após ativar o modo offline',
        timeout: 30_000,
      },
    )
    .toBe(true);
  await expect(page.locator('[data-testid="stSkeleton"]')).toHaveCount(0, {
    timeout: 30_000,
  });
}

test('KDS multi-setor executa aceite inicio pausa retomada pronto e retirada', async ({ page }) => {
  await abrirKDS(page);
  await selectComboboxOption(page, 'Setor', 'Cozinha quente');
  await aguardarProducao(page, 'prod-kds-quente');
  await aguardarStatus(page, 'aguardando');
  await expect(page.getByText(/^SLA:\s*(dentro|atencao|estourado)$/).last()).toBeVisible();

  await clicarEAguardarStatus(page, 'Aceitar', 'aceita');
  await clicarEAguardarStatus(page, 'Iniciar', 'em_preparo');

  const motivo = page.getByRole('textbox', { name: 'Motivo da pausa', exact: true });
  await motivo.fill('equipamento em ajuste');
  const pendente = page.getByText('Press Enter to apply', { exact: true });
  if (await pendente.count()) {
    await expect(pendente).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(pendente).toHaveCount(0, { timeout: 15_000 });
    await aguardarStatus(page, 'em_preparo');
  }
  await clicarEAguardarStatus(page, 'Pausar', 'pausada');
  await clicarEAguardarStatus(page, 'Retomar', 'em_preparo');
  await clicarEAguardarStatus(page, 'Marcar pronto', 'pronta');

  await page.getByRole('button', { name: 'Registrar retirada', exact: true }).click();
  await expect(page.getByText('Fila vazia para o filtro selecionado.', { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  // O setor de bebidas permanece independente e não herda o estado da cozinha quente.
  await selectComboboxOption(page, 'Setor', 'Bebidas');
  await aguardarProducao(page, 'prod-kds-bebida');
  await aguardarStatus(page, 'aguardando');
});

test('KDS offline preserva ultimo snapshot e bloqueia comandos', async ({ page }) => {
  await abrirKDS(page);
  await selectComboboxOption(page, 'Setor', 'Bebidas');
  await aguardarProducao(page, 'prod-kds-bebida');
  await aguardarStatus(page, 'aguardando');

  await ativarOffline(page);
  await expect(
    page.getByText('KDS em modo degradado — somente leitura', { exact: true }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByText('Exibindo o último snapshot conhecido; comandos estão bloqueados.', {
      exact: true,
    }),
  ).toBeVisible();
  await aguardarProducao(page, 'prod-kds-bebida');
  await aguardarStatus(page, 'aguardando');
  await expect(page.getByRole('button', { name: 'Aceitar', exact: true })).toHaveCount(0);
});
