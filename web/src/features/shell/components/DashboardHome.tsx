"use client";

import {
  Activity,
  ArrowRight,
  Bot,
  BrainCircuit,
  ChefHat,
  CircleGauge,
  LayoutGrid,
  Link as LinkIcon,
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
import { useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  availableShellModules,
  type ShellModuleDefinition,
  type ShellModuleIcon,
} from "@/features/shell/module-registry";

const iconByName: Record<ShellModuleIcon, typeof ShoppingCart> = {
  dashboard: ShieldCheck,
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

function ModuleCard({ module }: { module: ShellModuleDefinition }) {
  const Icon = iconByName[module.icon];
  const protectedModule = module.group === "proprietario";

  return (
    <Link href={module.href} className="group block h-full">
      <Card className="h-full overflow-hidden border-slate-200/80 bg-white/92 transition-all duration-200 hover:-translate-y-1 hover:border-blue-200 hover:shadow-[0_24px_55px_-30px_rgba(37,99,235,0.32)]">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex size-11 items-center justify-center rounded-2xl bg-[linear-gradient(145deg,#0f172a,#1e3a5f)] text-white shadow-[0_14px_28px_-18px_rgba(15,23,42,0.9)] ring-1 ring-white/10 transition group-hover:scale-[1.03] group-hover:bg-[linear-gradient(145deg,#1d4ed8,#0284c7)]">
              <Icon className="size-5" />
            </div>
            <Badge
              variant="outline"
              className={
                protectedModule
                  ? "border-amber-200/80 bg-amber-50/80 text-amber-700"
                  : "border-emerald-200/80 bg-emerald-50/80 text-emerald-700"
              }
            >
              {protectedModule ? "Acesso protegido" : "Disponível"}
            </Badge>
          </div>
          <CardTitle className="mt-4 text-lg tracking-tight text-slate-950 transition-colors group-hover:text-blue-700">
            {module.label}
          </CardTitle>
          <CardDescription className="min-h-12 leading-6 text-slate-500">
            {module.description}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <span className="inline-flex items-center gap-1.5 text-sm font-bold text-blue-700">
            Abrir módulo
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
          </span>
        </CardContent>
      </Card>
    </Link>
  );
}

export function DashboardHome() {
  const auth = useAuthStore();
  const modules = useMemo(
    () => availableShellModules(auth.permissions),
    [auth.permissions],
  );
  const operationModules = modules.filter((module) => module.group === "operacao");
  const proprietorModules = modules.filter(
    (module) => module.group === "proprietario",
  );
  const gerenteIa = modules.find((module) => module.id === "gerente-ia");
  const displayName =
    auth.operator?.nome?.trim() || auth.operator?.email || "usuário";

  return (
    <div className="kordena-page min-h-full px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <div className="kordena-enter mx-auto w-full max-w-7xl space-y-8">
        <section className="relative overflow-hidden rounded-[2rem] border border-slate-800/80 bg-[#08111f] p-6 text-white shadow-[0_30px_80px_-40px_rgba(2,6,23,0.8)] sm:p-8 lg:p-10">
          <div className="kordena-grid pointer-events-none absolute inset-0 opacity-70" />
          <div className="pointer-events-none absolute -right-28 -top-28 size-80 rounded-full bg-blue-500/22 blur-3xl" />
          <div className="pointer-events-none absolute bottom-[-8rem] left-[28%] size-72 rounded-full bg-cyan-400/10 blur-3xl" />

          <div className="relative grid gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.7fr)] lg:items-end">
            <div className="max-w-3xl">
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-emerald-400/15 bg-emerald-400/[0.07] px-3 py-1.5 text-xs font-bold text-emerald-200">
                <span className="size-1.5 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.95)]" />
                Sessão corporativa validada
              </div>
              <p className="text-xs font-black uppercase tracking-[0.24em] text-sky-300">
                Kordena Enterprise
              </p>
              <h1 className="mt-3 text-3xl font-black tracking-[-0.035em] sm:text-4xl lg:text-5xl">
                Central de operação e gestão
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-300 sm:text-base">
                Olá, {displayName}. Acesse somente os módulos liberados para sua função e para a unidade ativa da sessão.
              </p>

              {gerenteIa ? (
                <Link
                  href={gerenteIa.href}
                  className="mt-6 inline-flex items-center gap-3 rounded-2xl border border-blue-400/20 bg-blue-500/10 px-4 py-3 text-sm font-semibold text-blue-100 transition hover:-translate-y-0.5 hover:border-blue-300/30 hover:bg-blue-500/15"
                >
                  <span className="flex size-9 items-center justify-center rounded-xl bg-blue-500/15 ring-1 ring-blue-400/20">
                    <Sparkles className="size-4 text-sky-300" />
                  </span>
                  <span>
                    <span className="block text-xs font-black uppercase tracking-[0.14em] text-blue-300">Gerente IA</span>
                    <span className="mt-0.5 block text-xs text-slate-300">Consulte a operação e prepare decisões governadas</span>
                  </span>
                  <ArrowRight className="ml-2 size-4" />
                </Link>
              ) : null}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="kordena-glass rounded-2xl p-4">
                <p className="text-3xl font-black tabular-nums text-white">{operationModules.length}</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">módulos operacionais</p>
              </div>
              <div className="kordena-glass rounded-2xl p-4">
                <p className="text-3xl font-black tabular-nums text-white">{proprietorModules.length}</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">módulos de gestão</p>
              </div>
              <div className="col-span-2 rounded-2xl border border-white/[0.08] bg-white/[0.045] p-4 backdrop-blur">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                  <ShieldCheck className="size-4 text-emerald-300" />
                  Acesso orientado por função e unidade
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">
                  O shell respeita as permissões da identidade e o escopo operacional da sessão assinada.
                </p>
              </div>
            </div>
          </div>
        </section>

        {operationModules.length > 0 ? (
          <section>
            <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.2em] text-blue-700">
                  Operação
                </p>
                <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950">
                  Chão de fábrica
                </h2>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  Atendimento, produção e execução operacional disponíveis para sua função.
                </p>
              </div>
              <Badge variant="outline" className="border-slate-200 bg-white/70 text-slate-600">
                {operationModules.length} disponíveis
              </Badge>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {operationModules.map((module) => (
                <ModuleCard key={module.id} module={module} />
              ))}
            </div>
          </section>
        ) : null}

        {proprietorModules.length > 0 ? (
          <section>
            <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.2em] text-amber-700">
                  Gestão protegida
                </p>
                <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950">
                  Área do Proprietário
                </h2>
                <p className="mt-1 text-sm leading-6 text-slate-500">
                  A entrada permanece sujeita à permissão administrativa e à reautenticação temporária.
                </p>
              </div>
              <Badge variant="outline" className="border-amber-200 bg-amber-50/70 text-amber-700">
                Step-up protegido
              </Badge>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {proprietorModules.map((module) => (
                <ModuleCard key={module.id} module={module} />
              ))}
            </div>
          </section>
        ) : null}

        {modules.length === 0 ? (
          <section className="rounded-3xl border border-amber-200 bg-amber-50 p-6 text-amber-950 shadow-sm">
            <h2 className="text-lg font-bold">Nenhum módulo liberado para esta identidade</h2>
            <p className="mt-2 text-sm leading-6 text-amber-800">
              Sua sessão está autenticada, porém não há módulos Web disponíveis para as permissões atuais. Solicite ao administrador a revisão do seu papel e das suas permissões.
            </p>
          </section>
        ) : null}
      </div>
    </div>
  );
}
