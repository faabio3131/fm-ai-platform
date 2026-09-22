"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { ArrowLeft, Loader2, MailCheck, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createSignup, SignupApiError } from "@/features/auth/services/signup-api";

const SIGNUP_ENABLED = process.env.NEXT_PUBLIC_KORDENA_SIGNUP_ENABLED === "true";

export default function SignupPage() {
  const [submitting, setSubmitting] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    const data = new FormData(event.currentTarget);
    try {
      await createSignup({
        owner_name: String(data.get("owner_name") || ""),
        email: String(data.get("email") || ""),
        password: String(data.get("password") || ""),
        phone: String(data.get("phone") || ""),
        establishment_name: String(data.get("establishment_name") || ""),
        segment: String(data.get("segment") || ""),
        terms_accepted: data.get("terms_accepted") === "on",
        consents: { marketing: data.get("marketing") === "on" },
      });
      setAccepted(true);
    } catch (cause) {
      if (cause instanceof SignupApiError && cause.status === 429) {
        setError("Muitas tentativas. Aguarde alguns minutos e tente novamente.");
      } else {
        setError("Não foi possível iniciar o cadastro agora.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!SIGNUP_ENABLED) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#06101d] px-5 text-white">
        <section className="w-full max-w-lg rounded-[2rem] border border-white/[0.09] bg-slate-900/80 p-8 text-center">
          <ShieldCheck className="mx-auto size-10 text-blue-300" />
          <h1 className="mt-5 text-2xl font-black">Cadastro em preparação</h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            O fluxo técnico de teste grátis ainda não foi liberado ao público.
          </p>
          <Button asChild className="mt-6">
            <Link href="/login"><ArrowLeft />Voltar para entrar</Link>
          </Button>
        </section>
      </main>
    );
  }

  if (accepted) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#06101d] px-5 text-white">
        <section className="w-full max-w-lg rounded-[2rem] border border-white/[0.09] bg-slate-900/80 p-8 text-center">
          <MailCheck className="mx-auto size-10 text-emerald-300" />
          <h1 className="mt-5 text-2xl font-black">Confira seu e-mail</h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            Se os dados forem elegíveis, enviaremos as instruções de verificação.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#06101d] px-5 py-10 text-white">
      <section className="mx-auto w-full max-w-xl rounded-[2rem] border border-white/[0.09] bg-slate-900/80 p-6 sm:p-8">
        <Link href="/login" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
          <ArrowLeft className="size-4" /> Voltar
        </Link>
        <h1 className="mt-6 text-3xl font-black">Começar teste grátis</h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          Crie sua conta para iniciar o processo seguro de ativação do Kordena.
        </p>
        <form className="mt-7 space-y-4" onSubmit={(event) => void submit(event)}>
          <Input name="owner_name" aria-label="Nome do responsável" placeholder="Nome do responsável" required maxLength={255} />
          <Input name="email" aria-label="E-mail" type="email" placeholder="E-mail" required maxLength={320} />
          <Input name="phone" aria-label="Telefone ou WhatsApp" placeholder="Telefone ou WhatsApp" maxLength={64} />
          <Input name="password" aria-label="Senha" type="password" autoComplete="new-password" placeholder="Senha" required minLength={8} maxLength={1024} />
          <Input name="establishment_name" aria-label="Nome do estabelecimento" placeholder="Nome do estabelecimento" required maxLength={255} />
          <Input name="segment" aria-label="Segmento" placeholder="Segmento" required maxLength={96} />
          <label className="flex items-start gap-3 text-sm text-slate-300">
            <input name="terms_accepted" type="checkbox" required className="mt-1" />
            <span>Li e aceito os termos aplicáveis ao cadastro.</span>
          </label>
          <label className="flex items-start gap-3 text-sm text-slate-400">
            <input name="marketing" type="checkbox" className="mt-1" />
            <span>Aceito receber comunicações comerciais opcionais.</span>
          </label>
          {error ? <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-sm">{error}</div> : null}
          <Button type="submit" className="h-12 w-full" disabled={submitting}>
            {submitting ? <><Loader2 className="animate-spin" />Enviando…</> : "Continuar"}
          </Button>
        </form>
      </section>
    </main>
  );
}
