"use client";

import { ArrowLeft, Eye, EyeOff, Loader2, LockKeyhole, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { KordenaBrand } from "@/components/brand/KordenaBrand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AuthApiError, resetPassword } from "@/features/auth/services/auth-api";

export default function ResetPasswordPage() {
  const [token, setToken] = useState(() => {
    if (typeof window === "undefined") return "";
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    return params.get("token")?.trim() ?? "";
  });
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (window.location.hash) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!token) {
      setError("Este link de recuperação é inválido ou já foi utilizado.");
      return;
    }
    if (password.length < 10) {
      setError("A nova senha deve ter pelo menos 10 caracteres.");
      return;
    }
    if (password !== confirm) {
      setError("As senhas informadas não são iguais.");
      return;
    }

    setSubmitting(true);
    try {
      await resetPassword(token, password);
      setCompleted(true);
      setToken("");
      setPassword("");
      setConfirm("");
    } catch (cause) {
      if (cause instanceof AuthApiError && cause.status === 422) {
        setError("A nova senha não atende aos requisitos de segurança.");
      } else if (cause instanceof AuthApiError && cause.status === 400) {
        setError("Este link expirou, já foi utilizado ou não é válido.");
      } else {
        setError("Não foi possível redefinir a senha agora. Tente novamente.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="kordena-page-dark relative flex min-h-screen items-center justify-center overflow-hidden px-5 py-10 text-white">
      <div className="kordena-grid pointer-events-none absolute inset-0 opacity-35" />
      <section className="kordena-enter relative w-full max-w-md">
        <KordenaBrand className="mb-7" />
        <div className="rounded-[2rem] border border-white/[0.09] bg-slate-900/72 p-6 shadow-[0_34px_90px_-40px_rgba(0,0,0,0.85)] backdrop-blur-xl sm:p-8">
          <Link href="/login" className="inline-flex items-center gap-2 text-sm text-slate-400 transition hover:text-white">
            <ArrowLeft className="size-4" />
            Voltar para o login
          </Link>

          <div className="mt-6 flex size-12 items-center justify-center rounded-2xl bg-blue-500/10 text-blue-300 ring-1 ring-blue-400/15">
            <ShieldCheck className="size-6" />
          </div>

          {completed ? (
            <>
              <h1 className="mt-5 text-2xl font-black tracking-[-0.03em]">Senha alterada</h1>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Sua nova senha foi salva e todas as sessões anteriores foram encerradas por segurança.
              </p>
              <Button asChild className="mt-6 h-12 w-full">
                <Link href="/login">Entrar com a nova senha</Link>
              </Button>
            </>
          ) : (
            <>
              <h1 className="mt-5 text-2xl font-black tracking-[-0.03em]">Criar nova senha</h1>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Defina uma nova senha para seu acesso Kordena. O link é temporário e de uso único.
              </p>

              <form className="mt-7 space-y-5" onSubmit={(event) => void submit(event)}>
                <div className="space-y-2">
                  <label htmlFor="new-password" className="text-sm font-semibold text-slate-200">Nova senha</label>
                  <div className="relative">
                    <LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                    <Input
                      id="new-password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="new-password"
                      required
                      minLength={10}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      className="h-12 border-slate-700 bg-slate-950/65 px-10 text-white"
                    />
                    <button
                      type="button"
                      aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                      className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-500 transition hover:bg-white/[0.06] hover:text-slate-200"
                      onClick={() => setShowPassword((current) => !current)}
                    >
                      {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <label htmlFor="confirm-password" className="text-sm font-semibold text-slate-200">Confirmar nova senha</label>
                  <Input
                    id="confirm-password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    required
                    minLength={10}
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                    className="h-12 border-slate-700 bg-slate-950/65 text-white"
                  />
                </div>

                {error ? (
                  <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                    {error}
                  </div>
                ) : null}

                <Button type="submit" size="lg" className="h-12 w-full" disabled={submitting}>
                  {submitting ? (
                    <>
                      <Loader2 className="animate-spin" />
                      Salvando…
                    </>
                  ) : (
                    "Salvar nova senha"
                  )}
                </Button>
              </form>
            </>
          )}
        </div>
      </section>
    </main>
  );
}
