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
    <main className="kordena-page min-h-full px-4 py-4 sm:px-5 lg:px-6">
      <div className="kordena-enter mx-auto w-full max-w-[1500px] space-y-4">
        <header className="relative overflow-hidden rounded-[1.5rem] border border-slate-700/60 bg-[linear-gradient(145deg,rgba(15,30,51,0.98),rgba(8,20,36,0.98))] p-4 shadow-[0_24px_60px_-40px_rgba(0,0,0,0.88)] backdrop-blur sm:p-5">
          <div className="pointer-events-none absolute -right-20 -top-24 size-64 rounded-full bg-blue-500/10 blur-3xl" />
          <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-amber-300/20 bg-amber-400/[0.08] px-2.5 py-1 text-[11px] font-bold text-amber-200">
                <ShieldCheck className="size-3.5" />
                Área Proprietário · step-up validado
              </div>
              <p className="mt-3 text-[11px] font-black uppercase tracking-[0.2em] text-sky-300">Kordena Backoffice</p>
              <h1 className="mt-1.5 text-2xl font-black tracking-[-0.035em] text-slate-50 sm:text-3xl">Centro Administrativo</h1>
              <p className="mt-1.5 max-w-2xl text-[13px] leading-5 text-slate-500">
                Acesse as áreas de administração disponíveis para sua conta, mantendo a unidade ativa e as permissões da sessão como fonte de autoridade.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2.5 sm:min-w-64">
              <div className="rounded-xl border border-slate-700/55 bg-slate-950/32 p-3">
                <LayoutDashboard className="size-4 text-sky-300" />
                <p className="mt-2 text-xl font-black text-slate-50">{modules.length}</p>
                <p className="mt-1 text-xs text-slate-500">áreas disponíveis</p>
              </div>
              <div className="rounded-xl border border-slate-700/55 bg-slate-950/32 p-3">
                <Sparkles className="size-4 text-violet-400" />
                <p className="mt-2 text-[13px] font-black text-slate-50">Gestão integrada</p>
                <p className="mt-1 text-xs leading-5 text-slate-500">Operação, financeiro, fiscal e IA.</p>
              </div>
            </div>
          </div>
        </header>

        <nav aria-label="Áreas do Centro Administrativo" className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-3">
          {modules.map((module) => (
            <Link
              key={module.id}
              href={module.href}
              className="group rounded-2xl border border-slate-700/60 bg-[linear-gradient(145deg,rgba(15,30,51,0.97),rgba(8,20,36,0.97))] p-3.5 shadow-[0_20px_48px_-34px_rgba(0,0,0,0.82)] transition-all duration-200 hover:-translate-y-0.5 hover:border-sky-400/28 hover:shadow-[0_28px_62px_-34px_rgba(47,124,246,0.46)]"
            >
              <div className="flex items-start justify-between gap-4">
                <span className="flex size-9 items-center justify-center rounded-xl bg-slate-950 text-white shadow-lg shadow-slate-900/10">
                  <ShieldCheck className="size-4" />
                </span>
                <ArrowRight className="size-4 text-slate-400 transition-transform group-hover:translate-x-1 group-hover:text-sky-300" />
              </div>
              <h2 className="mt-3 text-[15px] font-bold tracking-tight text-slate-50 group-hover:text-sky-300">{module.label}</h2>
              <p className="mt-1 min-h-8 text-xs leading-4 text-slate-500">{module.description}</p>
            </Link>
          ))}
        </nav>

        {modules.length === 0 ? (
          <section className="rounded-3xl border border-amber-300/20 bg-amber-400/[0.07] p-6 text-amber-100">
            <h2 className="font-bold">Nenhuma área disponível para esta conta.</h2>
            <p className="mt-2 text-sm text-amber-800">Revise o papel e as permissões administrativas desta identidade.</p>
          </section>
        ) : null}
      </div>
    </main>
  );
}
