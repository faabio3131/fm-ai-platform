import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

function source(path) {
  return fs.readFileSync(new URL(path, import.meta.url), "utf8");
}

test("Visual Premium preserva o shell canônico e torna o Core explícito", () => {
  const shell = source("../src/features/shell/components/UnifiedAppShell.tsx");
  assert.match(shell, /availableShellModules/);
  assert.match(shell, /selectUnit/);
  assert.match(shell, /endAuthSession/);
  assert.match(shell, /Gerente IA/);
  assert.match(shell, /kordena-brand-mark/);
});

test("Visual Premium preserva contratos funcionais do Gerente IA", () => {
  const gerente = source("../src/features/gerente-ia/components/GerenteIAWorkspace.tsx");
  assert.match(gerente, /perguntarGerenteIA/);
  assert.match(gerente, /confirmarGerenteIA/);
  assert.match(gerente, /preview_id/);
  assert.match(gerente, /idempotency_key/);
  assert.match(gerente, /Cognição operacional governada/);
});

test("Visual Premium preserva checkout público e autoridade de preço do servidor", () => {
  const cardapio = source("../src/features/cardapio-publico/components/CardapioPublicoWorkspace.tsx");
  assert.match(cardapio, /finalizarCheckoutPublico/);
  assert.match(cardapio, /idempotency_key/);
  assert.match(cardapio, /O valor final é validado pelo servidor/);
  assert.match(cardapio, /Confirmar pedido/);
});

test("Visual Premium preserva autenticação e step-up administrativo", () => {
  const login = source("../src/app/login/page.tsx");
  const stepUp = source("../src/features/auth/components/AdminStepUpGuard.tsx");
  assert.match(login, /login\(email\.trim\(\), senha\)/);
  assert.match(login, /selectUnit/);
  assert.match(stepUp, /elevateAdminSession/);
  assert.match(stepUp, /admin\.acessar/);
  assert.match(stepUp, /Desbloquear área Proprietário/);
});

test("design system Premium inclui acessibilidade, dark root e redução de movimento", () => {
  const css = source("../src/app/globals.css");
  const layout = source("../src/app/layout.tsx");
  assert.match(css, /color-scheme:\s*dark/);
  assert.match(css, /--kordena-midnight:/);
  assert.match(css, /--kordena-cobalt:/);
  assert.match(css, /--kordena-cyan:/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /kordena-panel-dark/);
  assert.match(css, /kordena-brand-mark/);
  assert.match(css, /kordena-surface-raised/);
  assert.match(css, /scrollbar-width/);
  assert.match(layout, /className="dark"/);
});

test("Visual Premium elimina ilhas claras nos workspaces operacionais prioritários", () => {
  const sources = [
    source("../src/features/shell/components/UnifiedAppShell.tsx"),
    source("../src/features/shell/components/DashboardHome.tsx"),
    source("../src/features/backoffice/components/BackofficeHome.tsx"),
    source("../src/features/pdv/components/PDVUnifiedWorkspace.tsx"),
    source("../src/features/pdv/components/PDVTouchWorkspace.tsx"),
    source("../src/features/orders/components/OrdersCenterWorkspace.tsx"),
    source("../src/features/delivery/components/DeliveryWorkspace.tsx"),
    source("../src/features/entrega/components/EntregaWorkspace.tsx"),
  ];

  for (const file of sources) {
    assert.doesNotMatch(file, /bg-slate-100/);
    assert.doesNotMatch(file, /border-slate-200/);
    assert.doesNotMatch(file, /text-slate-950/);
  }
});

test("Visual Premium mantém identidade cognitiva consistente entre login e shell", () => {
  const login = source("../src/app/login/page.tsx");
  const shell = source("../src/features/shell/components/UnifiedAppShell.tsx");
  assert.match(login, /Cognitive Operations/);
  assert.match(shell, /Cognitive Operations/);
  assert.doesNotMatch(login, /Enterprise Operations/);
  assert.doesNotMatch(shell, /Enterprise Operations/);
});
