import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workspace = readFileSync(
  new URL("../src/features/backoffice/fiscal/components/FiscalWorkspace.tsx", import.meta.url),
  "utf8",
);
const panel = readFileSync(
  new URL("../src/features/backoffice/fiscal/components/FiscalOperationsPanel.tsx", import.meta.url),
  "utf8",
);
const api = readFileSync(
  new URL("../src/features/backoffice/fiscal/services/fiscal-api.ts", import.meta.url),
  "utf8",
);
const router = readFileSync(
  new URL("../../http_api/admin_fiscal_operations.py", import.meta.url),
  "utf8",
);
const application = readFileSync(
  new URL("../../application/fiscal_web_operations.py", import.meta.url),
  "utf8",
);

test("WP-035 integra Inbox, XML oficial, Smart Intake, reconciliação e manifestação na Central Fiscal", () => {
  assert.match(workspace, /FiscalOperationsPanel/);
  assert.match(panel, /Fiscal Inbox e Smart Intake/);
  assert.match(panel, /Importar XML oficial/);
  assert.match(panel, /Captura por IA/);
  assert.match(panel, /Reconciliar captura/);
  assert.match(panel, /Registrar manifestação/);
  assert.match(panel, /evidência preliminar/i);
  assert.match(api, /\/v1\/admin\/fiscal\/inbound\/xml/);
  assert.match(api, /\/manifest/);
  assert.match(api, /\/intake\/preliminary/);
  assert.match(api, /\/reconcile/);
});

test("WP-036 expõe procurement sem criar segunda autoridade de estoque ou compra no React", () => {
  assert.match(panel, /Fornecedores e vínculos/);
  assert.match(panel, /Pedido de compra/);
  assert.match(panel, /Recebimento físico/);
  assert.match(panel, /Confirmar recebimento/);
  assert.match(panel, /Devolver/);
  assert.match(api, /\/v1\/admin\/fiscal\/procurement/);
  assert.match(application, /ServicoProcurement/);
  assert.match(router, /Permissao\.FISCAL_COMPRAS_RECEBER/);
  assert.match(router, /Permissao\.COMPRA_APROVAR/);
});

test("WP-037 mantém financeiro-fiscal governado e sem pagamento implícito", () => {
  assert.match(panel, /Financeiro e crédito tributário/);
  assert.match(panel, /Criar obrigação da compra/);
  assert.match(panel, /Ajustar obrigação/);
  assert.match(panel, /Decisão de crédito tributário/);
  assert.match(panel, /sem executar pagamento/i);
  assert.match(panel, /environment !== "production"/);
  assert.match(api, /\/v1\/admin\/fiscal\/financial\/obligations/);
  assert.match(api, /\/financial\/adjustments/);
  assert.match(api, /\/financial\/tax-credit-decisions/);
  assert.match(router, /Permissao\.FINANCEIRO_COMPRAS_REGISTRAR/);
  assert.match(router, /Permissao\.FINANCEIRO_TRIBUTOS_DECIDIR/);
});

test("escopo tenant/unidade não é escolhido pela interface", () => {
  assert.doesNotMatch(panel, /tenant_id|unidade_id/);
  assert.match(api, /credentials: "include"/);
  assert.match(panel, /Tenant e unidade vêm exclusivamente da sessão autenticada/);
});
