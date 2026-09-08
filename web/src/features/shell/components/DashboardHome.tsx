"use client";

import {
  Activity,
  ArrowRight,
  ChefHat,
  LayoutGrid,
  Package,
  ShieldCheck,
  ShoppingCart,
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
  kds: ChefHat,
  catalogo: Package,
  saude: Activity,
};

function ModuleCard({ module }: { module: ShellModuleDefinition }) {
  const Icon = iconByName[module.icon];
  const protectedModule = module.group === "proprietario";

  return (
    <Link href={module.href} className="group block h-full">
      <Card className="h-full border-slate-200 bg-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-lg">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex size-11 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-sm">
              <Icon className="size-5" />
            </div>
            <Badge
              variant="outline"
              className={
                protectedModule
                  ? "border-amber-200 bg-amber-50 text-amber-700"
                  : "border-emerald-200 bg-emerald-50 text-emerald-700"
              }
            >
              {protectedModule ? "Acesso protegido" : "Disponível"}
            </Badge>
          </div>
          <CardTitle className="mt-4 text-lg tracking-tight text-slate-950 group-hover:text-blue-700">
            {module.label}
          </CardTitle>
          <CardDescription className="leading-6 text-slate-500">
            {module.description}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <span className="inline-flex items-center gap-1 text-sm font-semibold text-blue-700">
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
  const displayName =
    auth.operator?.nome?.trim() || auth.operator?.email || "usuário";

  return (
    <div className="min-h-full bg-slate-100 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <div className="mx-auto w-full max-w-7xl space-y-8">
        <section className="overflow-hidden rounded-3xl bg-slate-950 p-6 text-white shadow-xl sm:p-8">
          <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
            <div className="max-w-3xl">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-400/20 bg-blue-400/10 px-3 py-1.5 text-xs font-semibold text-blue-200">
                <ShieldCheck className="size-3.5" />
                Sessão corporativa validada
              </div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-blue-300">
                Kordena Enterprise
              </p>
              <h1 className="mt-2 text-3xl font-black tracking-tight sm:text-4xl">
                Central de operação e gestão
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300 sm:text-base">
                Olá, {displayName}. Acesse somente os módulos liberados para sua função e para a unidade ativa da sessão.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:min-w-72">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-2xl font-black">{operationModules.length}</p>
                <p className="mt-1 text-xs text-slate-400">módulos operacionais</p>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-2xl font-black">{proprietorModules.length}</p>
                <p className="mt-1 text-xs text-slate-400">módulos de gestão</p>
              </div>
            </div>
          </div>
        </section>

        {operationModules.length > 0 ? (
          <section>
            <div className="mb-4">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-700">
                Operação
              </p>
              <h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">
                Chão de fábrica
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Atendimento, produção e execução operacional disponíveis para sua função.
              </p>
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
            <div className="mb-4">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-amber-700">
                Gestão protegida
              </p>
              <h2 className="mt-1 text-2xl font-bold tracking-tight text-slate-950">
                Área do Proprietário
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                A entrada permanece sujeita à permissão administrativa e à reautenticação temporária.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {proprietorModules.map((module) => (
                <ModuleCard key={module.id} module={module} />
              ))}
            </div>
          </section>
        ) : null}

        {modules.length === 0 ? (
          <section className="rounded-3xl border border-amber-200 bg-amber-50 p-6 text-amber-950">
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
