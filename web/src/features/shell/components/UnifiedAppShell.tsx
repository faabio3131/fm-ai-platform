"use client";

import {
  Activity,
  Bot,
  BrainCircuit,
  Building2,
  ChefHat,
  CircleGauge,
  LayoutDashboard,
  LayoutGrid,
  Link as LinkIcon,
  LogOut,
  Package,
  Printer,
  ShieldCheck,
  ShoppingCart,
  SlidersHorizontal,
  Sparkles,
  Users,
  Utensils,
  Warehouse,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { UnitSelectorModal } from "@/features/auth/components/UnitSelectorModal";
import {
  getUnits,
  selectUnit,
  type AuthUnit,
} from "@/features/auth/services/auth-api";
import {
  endAuthSession,
  refreshAuthSession,
  useAuthStore,
} from "@/features/auth/store/auth-store";
import {
  availableShellModules,
  isShellModuleActive,
  type ShellModuleDefinition,
  type ShellModuleIcon,
} from "@/features/shell/module-registry";

const iconByName: Record<ShellModuleIcon, typeof LayoutDashboard> = {
  dashboard: LayoutDashboard,
  pdv: ShoppingCart,
  salao: LayoutGrid,
  garcom: Utensils,
  kds: ChefHat,
  catalogo: Package,
  estoque: Warehouse,
  crm: Users,
  financeiro: CircleGauge,
  ai: BrainCircuit,
  saude: Activity,
  usuarios: Users,
  configuracao: SlidersHorizontal,
  impressao: Printer,
  integracoes: LinkIcon,
  assistente: Bot,
};

function unitTitle(unit: AuthUnit | undefined): string {
  if (!unit) return "Selecionar unidade";
  return unit.nome?.trim() || unit.codigo?.trim() || "Unidade ativa";
}

function roleLabel(roles: readonly string[] | undefined): string {
  const role = roles?.[0];
  if (!role) return "Usuário autenticado";
  return role.replaceAll("_", " ");
}

function NavigationLink({
  module,
  pathname,
  compact = false,
}: {
  module: ShellModuleDefinition;
  pathname: string;
  compact?: boolean;
}) {
  const Icon = iconByName[module.icon];
  const active = isShellModuleActive(pathname, module);

  return (
    <Link
      href={module.href}
      aria-current={active ? "page" : undefined}
      className={[
        "group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all duration-200",
        active
          ? "bg-gradient-to-r from-blue-600 to-sky-500 text-white shadow-[0_14px_28px_-18px_rgba(37,99,235,0.9)]"
          : "text-slate-300 hover:bg-white/[0.06] hover:text-white",
        compact ? "shrink-0" : "w-full",
      ].join(" ")}
    >
      <span
        className={[
          "flex size-8 shrink-0 items-center justify-center rounded-lg transition-colors",
          active ? "bg-white/12" : "bg-white/[0.045] group-hover:bg-white/[0.08]",
        ].join(" ")}
      >
        <Icon className="size-4" />
      </span>
      <span className="truncate">{module.label}</span>
      {active && !compact ? (
        <span className="ml-auto size-1.5 rounded-full bg-white shadow-[0_0_14px_rgba(255,255,255,0.9)]" />
      ) : null}
    </Link>
  );
}

export function UnifiedAppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useAuthStore();
  const [units, setUnits] = useState<AuthUnit[]>([]);
  const [unitModalOpen, setUnitModalOpen] = useState(false);
  const [busyUnitId, setBusyUnitId] = useState<string | null>(null);
  const [unitLoadError, setUnitLoadError] = useState(false);
  const publicSurface = pathname === "/cardapio" || pathname.startsWith("/cardapio/");

  const modules = useMemo(() => availableShellModules(auth.permissions), [auth.permissions]);
  const operationModules = modules.filter((module) => module.group === "operacao");
  const proprietorModules = modules.filter((module) => module.group === "proprietario");
  const activeUnit = units.find((unit) => unit.id === auth.unitId);
  const gerenteIaAvailable = modules.some((module) => module.id === "gerente-ia");

  useEffect(() => {
    if (pathname === "/login" || publicSurface || auth.status !== "authenticated") return;
    let cancelled = false;
    void getUnits()
      .then((nextUnits) => {
        if (!cancelled) {
          setUnits(nextUnits);
          setUnitLoadError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setUnitLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [auth.status, pathname, auth.unitId, publicSurface]);

  if (pathname === "/login" || publicSurface) return children;

  async function handleSelectUnit(unit: AuthUnit): Promise<void> {
    setBusyUnitId(unit.id);
    setUnitLoadError(false);
    try {
      await selectUnit(unit.id);
      await refreshAuthSession();
      setUnitModalOpen(false);
      router.refresh();
    } catch {
      setUnitLoadError(true);
    } finally {
      setBusyUnitId(null);
    }
  }

  async function handleLogout(): Promise<void> {
    await endAuthSession();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#08111f] text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/[0.07] bg-[#08111f]/92 px-4 py-3 backdrop-blur-xl lg:px-6">
        <div className="mx-auto flex max-w-[1920px] items-center justify-between gap-4">
          <Link href="/" className="flex min-w-0 items-center gap-3">
            <span className="kordena-brand-mark flex size-10 shrink-0 items-center justify-center rounded-xl">
              <BrainCircuit className="relative z-10 size-5 text-white" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[15px] font-black tracking-[0.08em] text-white">
                KORDENA
              </span>
              <span className="hidden text-[9px] font-bold uppercase tracking-[0.22em] text-slate-500 sm:block">
                Enterprise Operations
              </span>
            </span>
          </Link>

          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="max-w-52 border-white/10 bg-white/[0.055] text-slate-100 shadow-none hover:border-blue-400/30 hover:bg-white/[0.09] hover:text-white"
              onClick={() => setUnitModalOpen(true)}
              disabled={Boolean(busyUnitId)}
            >
              <Building2 className="size-4 text-sky-300" />
              <span className="truncate">{unitTitle(activeUnit)}</span>
            </Button>

            <div className="hidden items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.035] px-3 py-1.5 md:flex">
              <span className="flex size-7 items-center justify-center rounded-lg bg-blue-500/10 text-blue-300">
                <ShieldCheck className="size-3.5" />
              </span>
              <span className="max-w-44 text-right">
                <span className="block truncate text-xs font-semibold text-slate-100">
                  {auth.operator?.nome?.trim() || auth.operator?.email || "Usuário"}
                </span>
                <span className="block truncate text-[10px] capitalize text-slate-500">
                  {roleLabel(auth.operator?.papeis)}
                </span>
              </span>
            </div>

            <div
              className="hidden items-center gap-1.5 rounded-full border border-emerald-400/15 bg-emerald-400/[0.07] px-2.5 py-1.5 text-[10px] font-bold text-emerald-300 xl:flex"
              title="Sessão autenticada e escopo de unidade validado"
            >
              <span className="size-1.5 rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.9)]" />
              Sessão segura
            </div>

            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="text-slate-400 hover:bg-white/[0.06] hover:text-white"
              aria-label="Sair do Kordena"
              onClick={() => void handleLogout()}
            >
              <LogOut className="size-4" />
            </Button>
          </div>
        </div>

        {unitLoadError ? (
          <p className="mx-auto mt-2 max-w-[1920px] rounded-lg border border-amber-400/15 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-200" role="status">
            Não foi possível atualizar a lista de unidades agora. A unidade da sessão permanece preservada.
          </p>
        ) : null}
      </header>

      <div className="mx-auto flex min-h-0 w-full max-w-[1920px] flex-1">
        <aside className="hidden w-72 shrink-0 flex-col border-r border-white/[0.065] bg-[linear-gradient(180deg,#08111f_0%,#0a1525_55%,#08111f_100%)] p-4 lg:flex">
          <nav className="space-y-6" aria-label="Navegação principal">
            <div className="space-y-1">
              <Link
                href="/"
                aria-current={pathname === "/" ? "page" : undefined}
                className={[
                  "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all duration-200",
                  pathname === "/"
                    ? "bg-gradient-to-r from-blue-600 to-sky-500 text-white shadow-[0_14px_28px_-18px_rgba(37,99,235,0.9)]"
                    : "text-slate-300 hover:bg-white/[0.06] hover:text-white",
                ].join(" ")}
              >
                <span className={[
                  "flex size-8 items-center justify-center rounded-lg",
                  pathname === "/" ? "bg-white/12" : "bg-white/[0.045] group-hover:bg-white/[0.08]",
                ].join(" ")}>
                  <CircleGauge className="size-4" />
                </span>
                Visão geral
              </Link>
            </div>

            {operationModules.length > 0 ? (
              <div>
                <p className="mb-2 px-3 text-[10px] font-black uppercase tracking-[0.2em] text-slate-600">
                  Operação
                </p>
                <div className="space-y-1">
                  {operationModules.map((module) => (
                    <NavigationLink key={module.id} module={module} pathname={pathname} />
                  ))}
                </div>
              </div>
            ) : null}

            {proprietorModules.length > 0 ? (
              <div>
                <p className="mb-2 px-3 text-[10px] font-black uppercase tracking-[0.2em] text-amber-400/55">
                  Proprietário
                </p>
                <div className="space-y-1">
                  {proprietorModules.map((module) => (
                    <NavigationLink key={module.id} module={module} pathname={pathname} />
                  ))}
                </div>
              </div>
            ) : null}
          </nav>

          <div className="mt-auto space-y-3 pt-6">
            {gerenteIaAvailable ? (
              <Link
                href="/gerente-ia"
                className="group block overflow-hidden rounded-2xl border border-blue-400/15 bg-[linear-gradient(145deg,rgba(37,99,235,0.15),rgba(14,165,233,0.06))] p-3.5 transition hover:border-blue-400/30 hover:bg-[linear-gradient(145deg,rgba(37,99,235,0.21),rgba(14,165,233,0.09))]"
              >
                <div className="flex items-center gap-3">
                  <span className="flex size-9 items-center justify-center rounded-xl bg-blue-500/15 text-blue-300 ring-1 ring-blue-400/20">
                    <Sparkles className="size-4" />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-xs font-bold text-white">Gerente IA</span>
                    <span className="mt-0.5 block truncate text-[10px] text-slate-500">Inteligência operacional governada</span>
                  </span>
                </div>
              </Link>
            ) : null}

            <div className="rounded-2xl border border-white/[0.065] bg-white/[0.035] p-3.5">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-600">Unidade operacional</p>
              <p className="mt-1.5 truncate text-xs font-semibold text-slate-300">{unitTitle(activeUnit)}</p>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col bg-[#f4f7fb]">
          <nav className="flex gap-2 overflow-x-auto border-b border-slate-200/80 bg-white/92 px-3 py-2.5 shadow-sm backdrop-blur lg:hidden" aria-label="Navegação móvel">
            <Link
              href="/"
              className={[
                "flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold",
                pathname === "/" ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600",
              ].join(" ")}
            >
              <CircleGauge className="size-4" />
              Início
            </Link>
            {modules.map((module) => (
              <NavigationLink key={module.id} module={module} pathname={pathname} compact />
            ))}
          </nav>
          <main className="min-h-0 min-w-0 flex-1 overflow-auto bg-[#f4f7fb] text-slate-950">
            {children}
          </main>
        </div>
      </div>

      <UnitSelectorModal
        open={unitModalOpen}
        units={units}
        activeUnitId={auth.unitId}
        busyUnitId={busyUnitId}
        onSelect={handleSelectUnit}
        onDismiss={() => setUnitModalOpen(false)}
      />
    </div>
  );
}
