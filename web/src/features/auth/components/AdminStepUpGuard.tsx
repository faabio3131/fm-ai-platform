"use client";

import {
  ArrowLeft,
  KeyRound,
  Loader2,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, type ReactNode, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AuthApiError,
  elevateAdminSession,
  getAdminStepUpStatus,
  type AdminStepUpStatus,
} from "@/features/auth/services/auth-api";
import { useAuthStore } from "@/features/auth/store/auth-store";

const ADMIN_PERMISSION = "admin.acessar";

function errorMessage(error: unknown): string {
  if (error instanceof AuthApiError) {
    if (error.status === 401) return "Senha inválida. Confirme sua identidade para continuar.";
    if (error.status === 403) return "Sua identidade não possui acesso à área Proprietário.";
    if (error.status === 503) return "A validação administrativa está temporariamente indisponível.";
  }
  return "Não foi possível validar o acesso administrativo agora.";
}

export function AdminStepUpGuard({ children }: { children: ReactNode }) {
  const auth = useAuthStore();
  const [status, setStatus] = useState<AdminStepUpStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [senha, setSenha] = useState("");
  const [error, setError] = useState<string | null>(null);
  const hasAdminPermission = auth.permissions.includes(ADMIN_PERMISSION);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.unitId) return;
    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      setLoading(true);
      setStatus(null);
      setSenha("");
      setError(null);

      void getAdminStepUpStatus()
        .then((nextStatus) => {
          if (!cancelled) setStatus(nextStatus);
        })
        .catch((caught: unknown) => {
          if (!cancelled) setError(errorMessage(caught));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [auth.status, auth.unitId]);

  async function handleStepUp(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await elevateAdminSession(senha);
      setSenha("");
      setStatus(await getAdminStepUpStatus());
    } catch (caught: unknown) {
      setSenha("");
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || auth.status === "idle" || auth.status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-white">
        <div className="flex items-center gap-3 text-sm text-slate-300">
          <Loader2 className="size-5 animate-spin text-blue-400" />
          Validando barreira Proprietário…
        </div>
      </main>
    );
  }

  if (
    auth.status === "authenticated" &&
    (!hasAdminPermission || status?.permitido === false)
  ) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-white">
        <div className="w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900 p-7 shadow-2xl shadow-black/40">
          <ShieldAlert className="size-9 text-amber-400" />
          <p className="mt-5 text-xs font-semibold uppercase tracking-[0.2em] text-amber-300">
            Área Proprietário
          </p>
          <h1 className="mt-2 text-2xl font-semibold">Acesso administrativo não autorizado</h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Sua sessão operacional permanece válida, mas esta identidade não possui a permissão admin.acessar.
          </p>
          <Button asChild className="mt-6 w-full">
            <Link href="/">
              <ArrowLeft />
              Voltar ao dashboard
            </Link>
          </Button>
        </div>
      </main>
    );
  }

  if (status?.elevado) {
    return children;
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 py-10 text-white">
      <div className="w-full max-w-md rounded-3xl border border-slate-800 bg-slate-900 p-7 shadow-2xl shadow-black/40">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-blue-600 shadow-lg shadow-blue-950/40">
          <KeyRound className="size-6" />
        </div>
        <p className="mt-6 text-xs font-semibold uppercase tracking-[0.2em] text-blue-300">
          Área Proprietário
        </p>
        <h1 className="mt-2 text-2xl font-semibold">Confirme sua identidade</h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          A sessão já está autenticada. Para configurações administrativas, confirme novamente sua senha. A elevação é temporária e é cancelada ao trocar de unidade ou encerrar a sessão.
        </p>

        <form className="mt-6 space-y-4" onSubmit={(event) => void handleStepUp(event)}>
          <div className="space-y-2">
            <label htmlFor="admin-step-up-password" className="text-sm font-medium text-slate-200">
              Senha da sua conta
            </label>
            <Input
              id="admin-step-up-password"
              type="password"
              autoComplete="current-password"
              required
              value={senha}
              onChange={(event) => setSenha(event.target.value)}
              className="h-12 border-slate-700 bg-slate-950 text-white"
            />
          </div>

          {error ? (
            <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          <Button type="submit" size="lg" className="h-12 w-full" disabled={submitting}>
            {submitting ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
            {submitting ? "Confirmando…" : "Desbloquear área Proprietário"}
          </Button>
          <Button asChild type="button" variant="ghost" className="h-11 w-full text-slate-400 hover:text-white">
            <Link href="/">
              <ArrowLeft />
              Voltar ao dashboard
            </Link>
          </Button>
        </form>
      </div>
    </main>
  );
}
