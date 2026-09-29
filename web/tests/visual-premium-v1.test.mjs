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
  assert.match(shell, /intelligenceModules/);
  assert.match(shell, />\s*Inteligência\s*</);
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
  assert.match(brain, /kordena-brain-mark-v2\.png/);
  assert.match(brain, /unoptimized/);
  assert.doesNotMatch(login, /Cognitive Operations/);
  assert.doesNotMatch(shell, /Cognitive Operations/);
  assert.doesNotMatch(login, /Enterprise Operations/);
  assert.doesNotMatch(shell, /Enterprise Operations/);
});

test("identidade Kordena usa o cérebro aprovado e elimina slogans antigos globalmente", () => {
  const asset = fs.readFileSync(new URL("../public/kordena-brain-mark-v2.png", import.meta.url));
  const digest = crypto.createHash("sha256").update(asset).digest("hex");
  assert.equal(digest, "beb2c7f1b092f734489d6535e9be628842bf2ec24b5789cf6e422a4cdca63fc9");
  assert.equal(asset.length, 8393);
  assert.equal(asset.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");

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

test("Gerente IA fica separado da operação sob o grupo Inteligência", () => {
  const registry = source("../src/features/shell/module-registry.ts");
  const shell = source("../src/features/shell/components/UnifiedAppShell.tsx");
  const dashboard = source("../src/features/shell/components/DashboardHome.tsx");

  assert.match(registry, /ShellModuleGroup = "operacao" \| "inteligencia" \| "proprietario"/);
  assert.match(registry, /id: "gerente-ia"[\s\S]*group: "inteligencia"/);
  assert.match(shell, />\s*Inteligência\s*</);
  assert.match(dashboard, /Camada cognitiva para consultar a operação/);
});


test("Atendente IA expõe sua capacidade operacional e comercial sem inventar saúde externa", () => {
  const assistente = source("../src/features/backoffice/assistente-atendimento/components/AssistenteAtendimentoWorkspace.tsx");

  assert.match(assistente, /Central de Atendimento IA/);
  assert.match(
    assistente,
    /<h1[^>]*>[\s\S]*Central de Atendimento IA[\s\S]*<\/h1>/,
  );
  assert.match(assistente, /Agente operacional e comercial conectado ao Kordena/);
  assert.match(assistente, /Pulso operacional/);
  assert.match(assistente, /Fila e conversão em tempo de operação/);
  assert.match(assistente, /O que a Central de Atendimento IA realmente faz/);
  assert.match(assistente, /WhatsApp multimodal/);
  assert.match(assistente, /Core de IA/);
  assert.match(assistente, /Pedidos e checkout/);
  assert.match(assistente, /Pagamentos/);
  assert.match(assistente, /Entrega inteligente/);
  assert.match(assistente, /Estoque/);
  assert.match(assistente, /Handoff humano/);
  assert.match(assistente, /depende de integração/);
  assert.match(assistente, /não\s+apresenta credencial externa como online sem healthcheck real/);
  assert.match(assistente, /listarConversas/);
  assert.match(assistente, /forcarHandoff/);
  assert.doesNotMatch(assistente, /bg-slate-100/);
  assert.doesNotMatch(assistente, /border-slate-200/);
});


test("Central de Atendimento IA fica aberta à operação e mantém configuração administrativa protegida", () => {
  const registry = source("../src/features/shell/module-registry.ts");
  const workspace = source("../src/features/backoffice/assistente-atendimento/components/AssistenteAtendimentoWorkspace.tsx");
  const page = source("../src/app/atendimento-ia/page.tsx");

  assert.match(registry, /id: "assistente-atendimento"[\s\S]*href: "\/atendimento-ia"[\s\S]*group: "operacao"/);
  assert.match(registry, /id: "assistente-atendimento"[\s\S]*allPermissions: \["atendimento\.visualizar"\]/);
  assert.match(workspace, /Abrir configuração protegida/);
  assert.match(workspace, /adminSurface/);
  assert.match(page, /AssistenteAtendimentoWorkspace/);
});

test("Marketplaces ficam visíveis à operação sem expor autoridade administrativa", () => {
  const marketplace = source("../src/features/orders/components/MarketplaceChannelPanel.tsx");

  assert.match(marketplace, /pedido\.visualizar/);
  assert.match(marketplace, /integracao\.gerenciar/);
  assert.match(marketplace, /iFood/);
  assert.match(marketplace, /Keeta/);
  assert.match(marketplace, /99Food/);
  assert.match(marketplace, /homologação pendente/);
  assert.match(marketplace, /Operação visível; credenciais, homologação e sincronização manual permanecem protegidas/);
  assert.doesNotMatch(marketplace, /if \(!canManage\) return null/);
});


test("Central de Atendimento IA tem marca visual do WhatsApp e sidecar operacional global", () => {
  const workspace = source("../src/features/backoffice/assistente-atendimento/components/AssistenteAtendimentoWorkspace.tsx");
  const shell = source("../src/features/shell/components/UnifiedAppShell.tsx");
  const sidecar = source("../src/features/backoffice/assistente-atendimento/components/AtendimentoSidecar.tsx");
  const whatsapp = source("../src/features/backoffice/assistente-atendimento/components/WhatsAppChannelMark.tsx");

  assert.match(workspace, /WhatsAppChannelMark/);
  assert.match(workspace, />\s*WhatsApp\s*</);
  assert.match(shell, /AtendimentoSidecar/);
  assert.match(shell, /atendimento\.visualizar/);
  assert.match(shell, /module\.id === "assistente-atendimento"[\s\S]*WhatsAppChannelMark/);
  assert.match(sidecar, /fixed bottom-0 right-0/);
  assert.match(sidecar, /Atualiza automaticamente a cada 15 segundos/);
  assert.match(sidecar, /listarConversas/);
  assert.match(sidecar, /Abrir Central completa/);
  assert.match(sidecar, /pathname\.startsWith\("\/atendimento-ia"\)/);
  assert.match(whatsapp, /MessageCircle/);
  assert.match(whatsapp, /Phone/);
});


test("Catálogo e Estoque ficam em Operação com mutações protegidas", () => {
  const registry = source("../src/features/shell/module-registry.ts");
  const catalogo = source("../src/features/backoffice/catalogo/components/CatalogoWorkspace.tsx");
  const tabela = source("../src/features/backoffice/catalogo/components/CatalogoTable.tsx");
  const estoque = source("../src/features/backoffice/estoque/components/EstoqueWorkspace.tsx");

  assert.match(registry, /id: "catalogo"[\s\S]*href: "\/catalogo"[\s\S]*group: "operacao"[\s\S]*catalogo\.visualizar/);
  assert.match(registry, /id: "estoque"[\s\S]*href: "\/estoque"[\s\S]*group: "operacao"[\s\S]*estoque\.visualizar/);
  assert.match(catalogo, /Abrir gestão protegida/);
  assert.match(catalogo, /readOnly=\{!canAdminister\}/);
  assert.match(tabela, /readOnly = false/);
  assert.match(estoque, /Visualização operacional ativa/);
  assert.match(estoque, /Abrir gestão protegida/);
});

test("Gerente IA é Centro Operacional Cognitivo sem ampliar autoridade", () => {
  const gerente = source("../src/features/gerente-ia/components/GerenteIAWorkspace.tsx");
  assert.match(gerente, /Centro operacional cognitivo/);
  assert.match(gerente, /availableShellModules\(auth\.permissions\)/);
  assert.match(gerente, /module\.group === "operacao"/);
  assert.match(gerente, /O Gerente IA não amplia autoridade/);
  assert.match(gerente, /PERGUNTAS_RAPIDAS/);
});

test("Marketplaces separam operação de credenciais e homologação", () => {
  const marketplace = source("../src/features/orders/components/MarketplaceChannelPanel.tsx");
  assert.match(marketplace, /Canais de venda integrados/);
  assert.match(marketplace, /operação liberada/);
  assert.match(marketplace, /Operação visível; credenciais, homologação e sincronização manual permanecem protegidas/);
  assert.match(marketplace, /99Food/);
  assert.match(marketplace, /homologação pendente/);
});


test("DashboardHome mantém densidade premium sem cards excessivamente altos", () => {
  const dashboard = source("../src/features/shell/components/DashboardHome.tsx");

  assert.match(dashboard, /<CardHeader className="p-4 pb-2">/);
  assert.match(dashboard, /size-10 items-center justify-center rounded-xl/);
  assert.match(dashboard, /mt-3 text-base tracking-tight/);
  assert.match(dashboard, /min-h-10 text-\[13px\] leading-5/);
  assert.match(dashboard, /<CardContent className="px-4 pb-4 pt-0">/);
  assert.match(dashboard, /space-y-6/);
  assert.match(dashboard, /grid gap-3 md:grid-cols-2 xl:grid-cols-3/);
});


test("DashboardHome mantém hero executivo compacto na primeira dobra", () => {
  const dashboard = source("../src/features/shell/components/DashboardHome.tsx");

  assert.match(dashboard, /rounded-\[1\.75rem\][\s\S]*p-5[\s\S]*sm:p-6[\s\S]*lg:p-7/);
  assert.match(dashboard, /grid gap-6 lg:grid-cols-\[minmax\(0,1\.5fr\)_minmax\(300px,0\.68fr\)\]/);
  assert.match(dashboard, /lg:text-\[2\.65rem\]/);
  assert.match(dashboard, /mt-4 inline-flex items-center gap-2\.5 rounded-xl/);
  assert.match(dashboard, /grid grid-cols-3 gap-2\.5/);
  assert.match(dashboard, /kordena-glass rounded-xl p-3/);
});
