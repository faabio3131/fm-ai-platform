"use client";

import { ArrowRight, LayoutDashboard, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { useAuthStore } from "@/features/auth/store/auth-store";
import { availableShellModules } from "@/features/shell/module-registry";
import { API_BASE_URL } from "@/lib/api";

export function BackofficeHome() {
  const auth = useAuthStore();
  const modules = availableShellModules(auth.permissions).filter(
    (module) => module.group === "proprietario" && module.href !== "/admin",
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void fetch(`${API_BASE_URL}/v1/admin/acesso`, {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      }).catch(() => undefined);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [auth.tenantId, auth.unitId]);

  return (
    <main className="kordena-page min-h-full px-4 py-6 sm:px-6 lg:px-8">
      <div className="kordena-enter mx-auto w-full max-w-7xl space-y-7">
        <header className="relative overflow-hidden rounded-[2rem] border border-slate-200/80 bg-white/90 p-6 shadow-[0_24px_70px_-38px_rgba(15,23,42,0.35)] backdrop-blur sm:p-8">
          <div className="pointer-events-none absolute -right-20 -top-24 size-64 rounded-full bg-blue-500/10 blur-3xl" />
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-bold text-amber-800">
                <ShieldCheck className="size-3.5" />
                Área Proprietário · step-up validado
              </div>
              <p className="mt-5 text-xs font-black uppercase tracking-[0.2em] text-blue-700">Kordena Backoffice</p>
              <h1 className="mt-2 text-3xl font-black tracking-[-0.035em] text-slate-950 sm:text-4xl">Centro Administrativo</h1>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-500">
                Acesse as áreas de administração disponíveis para sua conta, mantendo a unidade ativa e as permissões da sessão como fonte de autoridade.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:min-w-72">
              <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                <LayoutDashboard className="size-5 text-blue-600" />
                <p className="mt-3 text-2xl font-black text-slate-950">{modules.length}</p>
                <p className="mt-1 text-xs text-slate-500">áreas disponíveis</p>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
                <Sparkles className="size-5 text-violet-600" />
                <p className="mt-3 text-sm font-black text-slate-950">Gestão integrada</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">Operação, financeiro, fiscal e IA.</p>
              </div>
            </div>
          </div>
        </header>

        <nav aria-label="Áreas do Centro Administrativo" className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {modules.map((module) => (
            <Link
              key={module.id}
              href={module.href}
              className="group rounded-3xl border border-slate-200/80 bg-white/92 p-5 shadow-[0_18px_45px_-30px_rgba(15,23,42,0.35)] transition-all duration-200 hover:-translate-y-1 hover:border-blue-200 hover:shadow-[0_26px_60px_-34px_rgba(37,99,235,0.32)]"
            >
              <div className="flex items-start justify-between gap-4">
                <span className="flex size-11 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-lg shadow-slate-900/10">
                  <ShieldCheck className="size-5" />
                </span>
                <ArrowRight className="size-4 text-slate-400 transition-transform group-hover:translate-x-1 group-hover:text-blue-600" />
              </div>
              <h2 className="mt-5 text-lg font-bold tracking-tight text-slate-950 group-hover:text-blue-700">{module.label}</h2>
              <p className="mt-2 min-h-12 text-sm leading-6 text-slate-500">{module.description}</p>
            </Link>
          ))}
        </nav>

        {modules.length === 0 ? (
          <section className="rounded-3xl border border-amber-200 bg-amber-50 p-6 text-amber-950">
            <h2 className="font-bold">Nenhuma área disponível para esta conta.</h2>
            <p className="mt-2 text-sm text-amber-800">Revise o papel e as permissões administrativas desta identidade.</p>
          </section>
        ) : null}
      </div>
    </main>
  );
}
