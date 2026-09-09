export type ShellModuleGroup = "operacao" | "proprietario";

export type ShellModuleIcon =
  | "dashboard"
  | "pdv"
  | "salao"
  | "kds"
  | "catalogo"
  | "estoque"
  | "crm"
  | "financeiro"
  | "ai"
  | "saude";

export interface ShellModuleDefinition {
  id: string;
  label: string;
  description: string;
  href: string;
  group: ShellModuleGroup;
  icon: ShellModuleIcon;
  available: boolean;
  allPermissions?: readonly string[];
  anyPermissions?: readonly string[];
}

export const SHELL_MODULES: readonly ShellModuleDefinition[] = [
  {
    id: "pdv",
    label: "PDV Touch",
    description: "Balcão, caixa e finalização de pedidos.",
    href: "/pdv",
    group: "operacao",
    icon: "pdv",
    available: true,
    allPermissions: ["pdv.operar"],
  },
  {
    id: "salao",
    label: "Salão",
    description: "Mesas, comandas e atendimento do salão.",
    href: "/salao",
    group: "operacao",
    icon: "salao",
    available: true,
    allPermissions: ["pedido.visualizar"],
    anyPermissions: ["mesa.abrir", "comanda.alterar"],
  },
  {
    id: "pedidos",
    label: "Central de Pedidos",
    description: "Visão unificada de pedidos, canais, alertas e situação financeira.",
    href: "/pedidos",
    group: "operacao",
    icon: "dashboard",
    available: true,
    allPermissions: ["pedido.visualizar"],
  },
  {
    id: "delivery",
    label: "Delivery Próprio",
    description: "Pedidos do canal próprio, cotação, checkout e acompanhamento.",
    href: "/delivery",
    group: "operacao",
    icon: "pdv",
    available: true,
    allPermissions: ["cliente.visualizar", "pedido.visualizar"],
  },
  {
    id: "kds",
    label: "KDS Cozinha",
    description: "Fila de produção e acompanhamento da cozinha.",
    href: "/kds",
    group: "operacao",
    icon: "kds",
    available: true,
    allPermissions: ["producao.visualizar"],
  },
  {
    id: "entrega",
    label: "Expedição e Entrega",
    description: "Checklist, entregadores, custódia, rota e prova de entrega.",
    href: "/entrega",
    group: "operacao",
    icon: "salao",
    available: true,
    allPermissions: ["expedicao.operar"],
  },
  {
    id: "indicadores",
    label: "Indicadores",
    description: "Visão executiva, financeiro e operação consolidada.",
    href: "/admin/dashboard",
    group: "proprietario",
    icon: "financeiro",
    available: true,
    allPermissions: ["admin.acessar", "financeiro.visualizar"],
  },
  {
    id: "ai-finops",
    label: "AI FinOps",
    description: "Uso, custo, eficiência e mix dos modelos de IA.",
    href: "/admin/ai-finops",
    group: "proprietario",
    icon: "ai",
    available: true,
    allPermissions: ["admin.acessar"],
  },
  {
    id: "catalogo",
    label: "Catálogo",
    description: "Produtos e disponibilidade do cardápio.",
    href: "/admin/catalogo",
    group: "proprietario",
    icon: "catalogo",
    available: true,
    allPermissions: ["admin.acessar"],
  },
  {
    id: "estoque",
    label: "Estoque e Validades",
    description: "Almoxarifado, insumos, saldos, custos e vencimentos.",
    href: "/admin/estoque",
    group: "proprietario",
    icon: "estoque",
    available: true,
    allPermissions: ["admin.acessar", "estoque.visualizar"],
  },
  {
    id: "crm",
    label: "CRM e Cashback",
    description: "Clientes, histórico e fidelidade da unidade.",
    href: "/admin/crm",
    group: "proprietario",
    icon: "crm",
    available: true,
    allPermissions: ["admin.acessar", "cliente.visualizar"],
  },
  {
    id: "saude-sistema",
    label: "Saúde do sistema",
    description: "Conectividade e diagnóstico técnico protegido.",
    href: "/admin/system-health",
    group: "proprietario",
    icon: "saude",
    available: true,
    allPermissions: ["admin.acessar"],
  },
] as const;

export function canAccessShellModule(
  permissions: readonly string[],
  module: ShellModuleDefinition,
): boolean {
  const permissionSet = new Set(permissions);
  const allAllowed = (module.allPermissions ?? []).every((permission) =>
    permissionSet.has(permission),
  );
  const anyRequired = module.anyPermissions ?? [];
  const anyAllowed =
    anyRequired.length === 0 ||
    anyRequired.some((permission) => permissionSet.has(permission));

  return allAllowed && anyAllowed;
}

export function availableShellModules(
  permissions: readonly string[],
): ShellModuleDefinition[] {
  return SHELL_MODULES.filter(
    (module) => module.available && canAccessShellModule(permissions, module),
  );
}

export function isShellModuleActive(
  pathname: string,
  module: ShellModuleDefinition,
): boolean {
  return pathname === module.href || pathname.startsWith(`${module.href}/`);
}
