"use client";

import {
  ArrowRight,
  BrainCircuit,
  Building2,
  Eye,
  EyeOff,
  Loader2,
  LockKeyhole,
  Mail,
  ShieldCheck,
  Sparkles,
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
  if (!candidate || !candidate.startsWith("/") || candidate.startsWith("//")) return "/";
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
    if (auth.status === "authenticated" && !unitModalOpen) router.replace(safeDestination());
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
        setAuthenticated(await getMe());
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
    <main className="relative min-h-screen overflow-hidden bg-[#06101d] text-white lg:grid lg:grid-cols-[1.08fr_0.92fr]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_14%,rgba(37,99,235,0.24),transparent_30%),radial-gradient(circle_at_78%_82%,rgba(14,165,233,0.12),transparent_34%)]" />
      <div className="kordena-grid pointer-events-none absolute inset-0 opacity-35" />

      <section className="relative hidden min-h-screen overflow-hidden border-r border-white/[0.07] lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16">
        <div className="flex items-center gap-3">
          <span className="kordena-brand-mark flex size-11 items-center justify-center rounded-2xl">
            <BrainCircuit className="relative z-10 size-5" />
          </span>
          <div>
            <p className="text-sm font-black tracking-[0.1em]">KORDENA</p>
            <p className="text-[9px] font-bold uppercase tracking-[0.22em] text-slate-500">Enterprise Operations</p>
          </div>
        </div>

        <div className="max-w-2xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/15 bg-emerald-400/[0.07] px-3 py-1.5 text-xs font-bold text-emerald-200">
            <ShieldCheck className="size-3.5" />
            Ambiente operacional seguro
          </div>
          <h1 className="mt-6 text-5xl font-black leading-[1.02] tracking-[-0.05em] xl:text-6xl">
            Toda a operação.
            <span className="block bg-gradient-to-r from-blue-300 via-sky-300 to-cyan-300 bg-clip-text text-transparent">
              Uma única inteligência.
            </span>
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-400">
            Acesse PDV, cozinha, salão, gestão financeira e o Gerente IA com uma sessão única, escopo de tenant validado e unidade operacional controlada.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="kordena-glass rounded-2xl p-4">
            <LockKeyhole className="mb-3 size-5 text-blue-300" />
            <p className="font-bold text-slate-200">Sessão assinada</p>
            <p className="mt-1 text-xs leading-5 text-slate-500">Identidade e permissões verificadas no backend.</p>
          </div>
          <div className="kordena-glass rounded-2xl p-4">
            <Building2 className="mb-3 size-5 text-sky-300" />
            <p className="font-bold text-slate-200">Escopo por unidade</p>
            <p className="mt-1 text-xs leading-5 text-slate-500">A operação respeita tenant e unidade ativa.</p>
          </div>
        </div>
      </section>

      <section className="relative flex min-h-screen items-center justify-center px-5 py-10 sm:px-8 lg:px-12">
        <div className="kordena-enter w-full max-w-md">
          <div className="mb-7 flex items-center gap-3 lg:hidden">
            <span className="kordena-brand-mark flex size-11 items-center justify-center rounded-2xl">
              <BrainCircuit className="relative z-10 size-5" />
            </span>
            <div>
              <p className="text-sm font-black tracking-[0.1em]">KORDENA</p>
              <p className="text-[9px] font-bold uppercase tracking-[0.22em] text-slate-500">Enterprise Operations</p>
            </div>
          </div>

          <div className="rounded-[2rem] border border-white/[0.09] bg-slate-900/72 p-6 shadow-[0_34px_90px_-40px_rgba(0,0,0,0.85)] backdrop-blur-xl sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-blue-400/15 bg-blue-400/[0.07] px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.14em] text-blue-200">
                  <Sparkles className="size-3" />
                  Acesso corporativo
                </div>
                <h2 className="mt-5 text-2xl font-black tracking-[-0.03em]">Entrar no Kordena</h2>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  Use suas credenciais corporativas para iniciar uma sessão segura.
                </p>
              </div>
              <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-blue-500/10 text-blue-300 ring-1 ring-blue-400/15">
                <ShieldCheck className="size-6" />
              </span>
            </div>

            <form className="mt-7 space-y-5" onSubmit={(event) => void handleSubmit(event)}>
              <div className="space-y-2">
                <label htmlFor="email" className="text-sm font-semibold text-slate-200">E-mail</label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                  <Input
                    id="email"
                    type="email"
                    inputMode="email"
                    autoComplete="username"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="operador@empresa.com"
                    className="h-12 border-slate-700 bg-slate-950/65 pl-10 text-white placeholder:text-slate-600"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label htmlFor="senha" className="text-sm font-semibold text-slate-200">Senha</label>
                <div className="relative">
                  <LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                  <Input
                    id="senha"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    required
                    value={senha}
                    onChange={(event) => setSenha(event.target.value)}
                    placeholder="Sua senha"
                    className="h-12 border-slate-700 bg-slate-950/65 px-10 text-white placeholder:text-slate-600"
                  />
                  <button
                    type="button"
                    aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                    className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-500 transition hover:bg-white/[0.06] hover:text-slate-200 focus-visible:ring-2 focus-visible:ring-blue-500"
                    onClick={() => setShowPassword((current) => !current)}
                  >
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>

              {error ? (
                <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                  {error}
                </div>
              ) : null}

              <Button type="submit" size="lg" className="h-12 w-full text-base" disabled={submitting}>
                {submitting ? <><Loader2 className="animate-spin" />Validando acesso…</> : <>Entrar<ArrowRight /></>}
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
