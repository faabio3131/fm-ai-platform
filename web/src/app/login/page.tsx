"use client";

import {
  ArrowRight,
  Building2,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { UnitSelectorModal } from "@/features/auth/components/UnitSelectorModal";
import {
  AuthApiError,
  getMe,
  getUnits,
  login,
  selectUnit,
  type AuthUnit,
} from "@/features/auth/services/auth-api";
import {
  setAuthenticated,
  useAuthStore,
} from "@/features/auth/store/auth-store";

function safeDestination(): string {
  if (typeof window === "undefined") return "/";

  const candidate = new URLSearchParams(window.location.search).get("next");
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) {
    return "/";
  }
  return candidate;
}

function errorMessage(error: unknown): string {
  if (error instanceof AuthApiError) {
    if (error.status === 401) return "E-mail ou senha inválidos.";
    if (error.status === 503) return "O serviço de sessão está temporariamente indisponível.";
  }
  return "Não foi possível entrar agora. Verifique a conexão e tente novamente.";
}

export default function LoginPage() {
  const router = useRouter();
  const auth = useAuthStore();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [units, setUnits] = useState<AuthUnit[]>([]);
  const [unitModalOpen, setUnitModalOpen] = useState(false);
  const [busyUnitId, setBusyUnitId] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status === "authenticated" && !unitModalOpen) {
      router.replace(safeDestination());
    }
  }, [auth.status, router, unitModalOpen]);

  async function finishLogin(): Promise<void> {
    router.replace(safeDestination());
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      await login(email.trim(), senha);
      const [operator, allowedUnits] = await Promise.all([getMe(), getUnits()]);
      setAuthenticated(operator);
      setUnits(allowedUnits);

      if (allowedUnits.length > 1) {
        setUnitModalOpen(true);
        return;
      }

      await finishLogin();
    } catch (submitError: unknown) {
      setError(errorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUnitSelection(unit: AuthUnit): Promise<void> {
    if (busyUnitId) return;
    setBusyUnitId(unit.id);
    setError(null);

    try {
      if (unit.id !== auth.unitId) {
        await selectUnit(unit.id);
        const operator = await getMe();
        setAuthenticated(operator);
      }
      setUnitModalOpen(false);
      await finishLogin();
    } catch (selectionError: unknown) {
      setError(errorMessage(selectionError));
    } finally {
      setBusyUnitId(null);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white lg:grid lg:grid-cols-[1.05fr_0.95fr]">
      <section className="relative hidden overflow-hidden border-r border-slate-800 lg:flex lg:min-h-screen lg:flex-col lg:justify-between lg:p-12 xl:p-16">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgba(37,99,235,0.24),transparent_34%),radial-gradient(circle_at_80%_80%,rgba(14,165,233,0.14),transparent_35%)]" />
        <div className="relative">
          <div className="inline-flex items-center gap-3 rounded-full border border-blue-400/20 bg-blue-500/10 px-4 py-2 text-sm text-blue-200">
            <ShieldCheck className="size-4" />
            Ambiente operacional seguro
          </div>
        </div>

        <div className="relative max-w-xl">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-blue-300">
            Kordena Enterprise
          </p>
          <h1 className="mt-5 text-5xl font-semibold leading-[1.05] tracking-tight xl:text-6xl">
            Sua operação começa com a identidade certa.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-slate-300">
            Acesse PDV, cozinha e salão com uma sessão única, escopo de tenant validado e unidade operacional controlada.
          </p>
        </div>

        <div className="relative grid grid-cols-2 gap-4 text-sm text-slate-300">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 backdrop-blur">
            <LockKeyhole className="mb-3 size-5 text-blue-300" />
            Sessão assinada e protegida
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 backdrop-blur">
            <Building2 className="mb-3 size-5 text-blue-300" />
            Unidade ativa sob seu escopo
          </div>
        </div>
      </section>

      <section className="flex min-h-screen items-center justify-center px-5 py-10 sm:px-8 lg:px-12">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-300">
              Kordena Enterprise
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight">Acesso operacional</h1>
          </div>

          <div className="rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl shadow-black/30 backdrop-blur sm:p-8">
            <div>
              <div className="flex size-12 items-center justify-center rounded-2xl bg-blue-600 shadow-lg shadow-blue-950/40">
                <ShieldCheck className="size-6" />
              </div>
              <h2 className="mt-6 text-2xl font-semibold tracking-tight">Entrar no Kordena</h2>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Use suas credenciais corporativas para iniciar uma sessão segura.
              </p>
            </div>

            <form className="mt-7 space-y-5" onSubmit={(event) => void handleSubmit(event)}>
              <div className="space-y-2">
                <label htmlFor="email" className="text-sm font-medium text-slate-200">
                  E-mail
                </label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                  <Input
                    id="email"
                    type="email"
                    inputMode="email"
                    autoComplete="username"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="operador@empresa.com"
                    className="h-12 border-slate-700 bg-slate-950/70 pl-10 text-white placeholder:text-slate-600"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label htmlFor="senha" className="text-sm font-medium text-slate-200">
                  Senha
                </label>
                <div className="relative">
                  <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                  <Input
                    id="senha"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={senha}
                    onChange={(event) => setSenha(event.target.value)}
                    placeholder="Sua senha"
                    className="h-12 border-slate-700 bg-slate-950/70 px-10 text-white placeholder:text-slate-600"
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-slate-500 transition hover:text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                    onClick={() => setShowPassword((current) => !current)}
                  >
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>

              {error ? (
                <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                  {error}
                </div>
              ) : null}

              <Button type="submit" size="lg" className="h-12 w-full text-base" disabled={submitting}>
                {submitting ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Validando acesso…
                  </>
                ) : (
                  <>
                    Entrar
                    <ArrowRight className="size-4" />
                  </>
                )}
              </Button>
            </form>

            <p className="mt-6 text-center text-xs leading-5 text-slate-500">
              O acesso é vinculado ao seu tenant, unidades permitidas e permissões ativas.
            </p>
          </div>
        </div>
      </section>

      <UnitSelectorModal
        open={unitModalOpen}
        units={units}
        activeUnitId={auth.unitId}
        busyUnitId={busyUnitId}
        onSelect={handleUnitSelection}
        onDismiss={() => {
          setUnitModalOpen(false);
          void finishLogin();
        }}
      />
    </main>
  );
}
