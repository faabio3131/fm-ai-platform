import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

function source(relativePath) {
  return fs.readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

function sourceFiles(root) {
  const entries = fs.readdirSync(root, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const resolved = path.join(root, entry.name);
    if (entry.isDirectory()) return sourceFiles(resolved);
    return /\.(?:ts|tsx|js|mjs)$/.test(entry.name) ? [resolved] : [];
  });
}

test("Visual Premium preserva o shell canônico e torna o Core explícito", () => {
  const shell = source("../src/features/shell/components/UnifiedAppShell.tsx");
  assert.match(shell, /availableShellModules/);
  assert.match(shell, /selectUnit/);
  assert.match(shell, /endAuthSession/);
  assert.match(shell, /Gerente IA/);
  assert.match(shell, /KordenaBrand/);
});

test("Visual Premium preserva contratos funcionais do Gerente IA", () => {
  const gerente = source("../src/features/gerente-ia/components/GerenteIAWorkspace.tsx");
  assert.match(gerente, /perguntarGerenteIA/);
  assert.match(gerente, /confirmarGerenteIA/);
  assert.match(gerente, /preview_id/);
  assert.match(gerente, /idempotency_key/);
  assert.match(gerente, /Cognição operacional governada/);
  assert.match(gerente, /KordenaBrainMark/);
  assert.doesNotMatch(gerente, /kordena-brand-mark/);
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

  const orders = source("../src/features/orders/components/OrdersCenterWorkspace.tsx");
  assert.doesNotMatch(orders, /\bbg-blue-50(?:\/\d+)?\b/);
  assert.doesNotMatch(orders, /text-slate-800/);
});

test("Visual Premium mantém identidade cognitiva consistente entre login e shell", () => {
  const login = source("../src/app/login/page.tsx");
  const shell = source("../src/features/shell/components/UnifiedAppShell.tsx");
  const brand = source("../src/components/brand/KordenaBrand.tsx");
  assert.match(login, /KordenaBrand/);
  assert.match(shell, /KordenaBrand/);
  assert.match(brand, /O CÉREBRO DA SUA OPERAÇÃO/);
  const brain = source("../src/components/brand/KordenaBrainMark.tsx");
  assert.match(brain, /kordena-brain-mark\.png/);
  assert.match(brain, /unoptimized/);
  assert.doesNotMatch(login, /Cognitive Operations/);
  assert.doesNotMatch(shell, /Cognitive Operations/);
  assert.doesNotMatch(login, /Enterprise Operations/);
  assert.doesNotMatch(shell, /Enterprise Operations/);
});

test("identidade Kordena usa o cérebro aprovado e elimina slogans antigos globalmente", () => {
  const asset = fs.readFileSync(new URL("../public/kordena-brain-mark.png", import.meta.url));
  const digest = crypto.createHash("sha256").update(asset).digest("hex");
  assert.equal(digest, "8e775411ec343026713d583197ae4cffb57a9b0a481c5e775cb0a591fc823a76");

  const sourceRoot = fileURLToPath(new URL("../src/", import.meta.url));
  for (const file of sourceFiles(sourceRoot)) {
    const content = fs.readFileSync(file, "utf8");
    assert.doesNotMatch(content, /Cognitive Operations/, file);
    assert.doesNotMatch(content, /Enterprise Operations/, file);
  }

  const dashboard = source("../src/features/shell/components/DashboardHome.tsx");
  const shell = source("../src/features/shell/components/UnifiedAppShell.tsx");
  const gerente = source("../src/features/gerente-ia/components/GerenteIAWorkspace.tsx");
  assert.match(dashboard, /module\.id === "gerente-ia"[\s\S]*KordenaBrainMark/);
  assert.match(shell, /module\.id === "gerente-ia"[\s\S]*KordenaBrainMark/);
  assert.match(gerente, /KordenaBrainMark/);
});
