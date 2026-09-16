"use client";

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
    // Como no original, falha da auditoria não substitui o guard de acesso.
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
    <main className="mx-auto w-full max-w-5xl space-y-6 p-6 text-slate-100">
      <header>
        <h1 className="text-2xl font-semibold">Centro Administrativo</h1>
        <p className="mt-2 text-sm text-slate-400">
          Acesse as áreas de administração disponíveis para sua conta.
        </p>
      </header>
      <nav aria-label="Áreas do Centro Administrativo" className="grid gap-4 sm:grid-cols-2">
        {modules.map((module) => (
          <Link key={module.id} href={module.href} className="rounded-xl border border-slate-800 bg-slate-900 p-5 hover:border-blue-500">
            <h2 className="font-semibold">{module.label}</h2>
            <p className="mt-2 text-sm text-slate-400">{module.description}</p>
          </Link>
        ))}
      </nav>
      {modules.length === 0 ? <p>Nenhuma área disponível para esta conta.</p> : null}
    </main>
  );
}
