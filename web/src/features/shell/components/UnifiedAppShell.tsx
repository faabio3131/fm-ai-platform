"use client";

import {
  Activity,
  BrainCircuit,
  Building2,
  ChefHat,
  CircleGauge,
  LayoutDashboard,
  LayoutGrid,
  LogOut,
  Package,
  ShieldCheck,
  ShoppingCart,
  Users,
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
  kds: ChefHat,
  catalogo: Package,
  estoque: Warehouse,
  crm: Users,
  financeiro: CircleGauge,
  ai: BrainCircuit,
  saude: Activity,
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
        "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
        active
          ? "bg-blue-600 text-white shadow-lg shadow-blue-950/20"
          : "text-slate-300 hover:bg-slate-800 hover:text-white",
        compact ? "shrink-0" : "w-full",
      ].join(" ")}
    >
      <Icon className="size-4 shrink-0" />
      <span>{module.label}</span>
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

  const modules = useMemo(
    () => availableShellModules(auth.permissions),
    [auth.permissions],
  );
  const operationModules = modules.filter((module) => module.group === "operacao");
  const proprietorModules = modules.filter(
    (module) => module.group === "proprietario",
  );
  const activeUnit = units.find((unit) => unit.id === auth.unitId);

  useEffect(() => {
    if (pathname === "/login" || auth.status !== "authenticated") return;

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
  }, [auth.status, pathname, auth.unitId]);

  if (pathname === "/login") {
    return children;
  }

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
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-950/95 px-4 py-3 backdrop-blur lg:px-6">
        <div className="flex items-center justify-between gap-4">
          <Link href="/" className="min-w-0">
            <p className="truncate text-base font-black tracking-tight text-white">
              KORDENA <span className="text-blue-400">ENTERPRISE</span>
            </p>
            <p className="hidden text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500 sm:block">
              Plataforma operacional de alimentação
            </p>
          </Link>

          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="max-w-48 border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800 hover:text-white"
              onClick={() => setUnitModalOpen(true)}
              disabled={Boolean(busyUnitId)}
            >
              <Building2 className="size-4 text-blue-400" />
              <span className="truncate">{unitTitle(activeUnit)}</span>
            </Button>

            <div className="hidden max-w-48 text-right md:block">
              <p className="truncate text-xs font-semibold text-slate-100">
                {auth.operator?.nome?.trim() || auth.operator?.email || "Usuário"}
              </p>
              <p className="truncate text-[10px] capitalize text-slate-500">
                {roleLabel(auth.operator?.papeis)}
              </p>
            </div>

            <div
              className="hidden items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-semibold text-emerald-300 xl:flex"
              title="Sessão autenticada e escopo de unidade validado"
            >
              <ShieldCheck className="size-3" />
              Sessão segura
            </div>

            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="text-slate-400 hover:bg-slate-900 hover:text-white"
              aria-label="Sair do Kordena"
              onClick={() => void handleLogout()}
            >
              <LogOut className="size-4" />
            </Button>
          </div>
        </div>

        {unitLoadError ? (
          <p className="mt-2 text-xs text-amber-300" role="status">
            Não foi possível atualizar a lista de unidades agora. A unidade da sessão permanece preservada.
          </p>
        ) : null}
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-950 p-4 lg:flex">
          <nav className="space-y-6" aria-label="Navegação principal">
            <div className="space-y-1">
              <Link
                href="/"
                aria-current={pathname === "/" ? "page" : undefined}
                className={[
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                  pathname === "/"
                    ? "bg-blue-600 text-white"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white",
                ].join(" ")}
              >
                <CircleGauge className="size-4" />
                Visão geral
              </Link>
            </div>

            {operationModules.length > 0 ? (
              <div>
                <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
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
                <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-[0.18em] text-amber-400/70">
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

          <div className="mt-auto rounded-2xl border border-slate-800 bg-slate-900/70 p-3">
            <p className="text-xs font-semibold text-slate-200">Unidade operacional</p>
            <p className="mt-1 truncate text-xs text-slate-500">{unitTitle(activeUnit)}</p>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <nav
            className="flex gap-2 overflow-x-auto border-b border-slate-800 bg-slate-950 px-3 py-2 lg:hidden"
            aria-label="Navegação móvel"
          >
            <Link
              href="/"
              className={[
                "flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium",
                pathname === "/" ? "bg-blue-600 text-white" : "bg-slate-900 text-slate-300",
              ].join(" ")}
            >
              <CircleGauge className="size-4" />
              Início
            </Link>
            {modules.map((module) => (
              <NavigationLink
                key={module.id}
                module={module}
                pathname={pathname}
                compact
              />
            ))}
          </nav>

          <main className="min-h-0 min-w-0 flex-1 overflow-auto bg-slate-100 text-slate-950">
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
