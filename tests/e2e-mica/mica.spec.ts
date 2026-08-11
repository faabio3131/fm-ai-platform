import { expect, test } from '@playwright/test';
import {
  clickAndWaitForStreamlitRerun,
  openTab,
  waitForAppReady,
} from '../e2e/fixtures/ui';


test('Mica valida carrinho e mantém Pix pendente até fonte financeira', async ({ page }) => {
  await waitForAppReady(page);
  await openTab(page, 'Bot Cliente');

  await expect(page.getByText('Mica I.A. — Atendimento seguro V1')).toBeVisible();
  await page.getByRole('textbox', { name: 'Mensagem do cliente' }).fill('Quero um Burger Teste');
  await clickAndWaitForStreamlitRerun(page, 'Analisar pedido com a Mica');

  await expect(page.getByText('Conferência do carrinho')).toBeVisible();
  await expect(page.getByText(/1x Burger Teste/)).toBeVisible();
  await expect(page.getByText(/Total: R\$ 29\.90/)).toBeVisible();
  await expect(page.getByText(/Nada foi cobrado nem enviado à produção ainda/)).toBeVisible();

  const confirmacao = page.getByRole('checkbox', {
    name: /Confirmo que o cliente revisou e aprovou exatamente este carrinho/,
  });
  const readyMarker = page.locator('[data-fm-ai-e2e-ready="true"]');
  const runAntes = await readyMarker.getAttribute('data-fm-ai-e2e-run');
  await confirmacao.evaluate((element: HTMLInputElement) => element.click());
  await expect
    .poll(async () => (await readyMarker.getAttribute('data-fm-ai-e2e-run')) !== runAntes, {
      timeout: 30_000,
    })
    .toBe(true);
  await expect(confirmacao).toBeChecked();
  await clickAndWaitForStreamlitRerun(page, 'Confirmar pedido');

  await expect(page.getByText(/Pagamento ainda pendente de confirmação financeira/)).toBeVisible();
  await expect(page.getByText(/Pagamento: .*pendente/)).toBeVisible();
  await expect(page.locator('body')).not.toContainText('Venda integrada no PDV');
  await expect(page.locator('body')).not.toContainText('estoque baixado com sucesso');
  await expect(page.locator('body')).not.toContainText('Traceback');
});


test('erro de interpretação faz handoff sem inventar pedido', async ({ page }) => {
  await waitForAppReady(page);
  await openTab(page, 'Bot Cliente');
  await page.getByRole('textbox', { name: 'Mensagem do cliente' }).fill('FM_AI_MOCK_INVALID');
  await clickAndWaitForStreamlitRerun(page, 'Analisar pedido com a Mica');

  await expect(page.getByText(/Atendimento humano solicitado: schema_mica_invalido/)).toBeVisible();
  await expect(page.getByText('Conferência do carrinho')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Confirmar pedido' })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Traceback');
});
