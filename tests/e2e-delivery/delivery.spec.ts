import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Delivery Próprio', { exact: true })).toBeVisible();
});

test('jornada própria calcula entrega, aplica benefícios e mantém Pix pendente', async ({ page }) => {
  await page.getByRole('button', { name: /Adicionar Burger Delivery/ }).click();
  await page.getByRole('button', { name: /Calcular entrega/ }).click();
  await expect(page.getByText(/Área Centro: taxa R\$ 7\.00/)).toBeVisible();

  await page.getByRole('button', { name: /Aplicar cupom/ }).click();
  await expect(page.getByText(/Desconto cupom: R\$ 3\.20/)).toBeVisible();

  await page.getByRole('button', { name: /Reservar cashback/ }).click();
  await expect(page.getByText(/Cashback: R\$ 5\.00/)).toBeVisible();
  await expect(page.getByText(/R\$ 30\.80/).last()).toBeVisible();

  await page.getByLabel('Forma de pagamento').selectOption({ label: 'Pix' });
  await page.getByRole('button', { name: /Confirmar pedido/ }).click();

  await expect(page.getByText('Pedido confirmado', { exact: true })).toBeVisible();
  await expect(page.getByText(/Pagamento: pendente/)).toBeVisible();
  await expect(page.getByText(/aguardando_producao: Pedido confirmado/)).toBeVisible();
  await expect(page.getByText(/nunca considera Pix\/cartão pago/)).toBeVisible();
});

test('CEP fora da área é bloqueado sem criar pedido', async ({ page }) => {
  await page.getByRole('button', { name: /Adicionar Burger Delivery/ }).click();
  await page.getByLabel('CEP').fill('99999999');
  await page.getByRole('button', { name: /Calcular entrega/ }).click();
  await expect(page.getByText(/fora_da_area_de_entrega/)).toBeVisible();
  await expect(page.getByText('Pedido confirmado', { exact: true })).toHaveCount(0);
});

test('pagamento na entrega não vira pago e cancelamento reconcilia a jornada', async ({ page }) => {
  await page.getByRole('button', { name: /Adicionar Burger Delivery/ }).click();
  await page.getByRole('button', { name: /Calcular entrega/ }).click();
  await page.getByLabel('Forma de pagamento').selectOption({ label: 'Pagamento na entrega' });
  await page.getByRole('button', { name: /Confirmar pedido/ }).click();

  await expect(page.getByText(/Pagamento: aguardando_entrega/)).toBeVisible();
  await page.getByText('Cancelar pedido', { exact: true }).click();
  await page.getByRole('button', { name: /Cancelar pedido agora/ }).click();
  await expect(page.getByText('Pedido cancelado.', { exact: true })).toBeVisible();
  await expect(page.getByText(/cancelada: Entrega cancelada/)).toBeVisible();
});
