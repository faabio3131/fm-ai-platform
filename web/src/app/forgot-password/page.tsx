"use client";

import { ArrowLeft, Loader2, Mail, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

import { KordenaBrand } from "@/components/brand/KordenaBrand";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AuthApiError,
  requestPasswordRecovery,
} from "@/features/auth/services/auth-api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await requestPasswordRecovery(email.trim());
      setAccepted(true);
    } catch (cause) {
      if (cause instanceof AuthApiError && cause.status === 422) {
        setError("Informe um e-mail válido.");
      } else {
        setError("Não foi possível solicitar a recuperação agora. Tente novamente.");
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

          <h1 className="mt-5 text-2xl font-black tracking-[-0.03em]">Recuperar sua senha</h1>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            Informe o e-mail do seu acesso Kordena. Se existir uma conta elegível,
            enviaremos um link seguro para criar uma nova senha.
          </p>

          {accepted ? (
            <div className="mt-7 rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.07] p-5">
              <p className="font-bold text-emerald-100">Confira seu e-mail</p>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                Se existir uma conta elegível com esse e-mail, as instruções de
                recuperação serão enviadas. O link expira em 30 minutos e pode ser
                usado uma única vez.
              </p>
              <Button asChild className="mt-5 w-full">
                <Link href="/login">Voltar para entrar</Link>
              </Button>
            </div>
          ) : (
            <form className="mt-7 space-y-5" onSubmit={(event) => void submit(event)}>
              <div className="space-y-2">
                <label htmlFor="recovery-email" className="text-sm font-semibold text-slate-200">E-mail</label>
                <div className="relative">
                  <Mail className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                  <Input
                    id="recovery-email"
                    type="email"
                    inputMode="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="voce@empresa.com"
                    className="h-12 border-slate-700 bg-slate-950/65 pl-10 text-white placeholder:text-slate-600"
                  />
                </div>
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
                    Enviando…
                  </>
                ) : (
                  "Enviar link de recuperação"
                )}
              </Button>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}
