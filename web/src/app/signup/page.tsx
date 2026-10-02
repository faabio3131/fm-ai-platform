"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { ArrowLeft, Loader2, MailCheck, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createSignup, SignupApiError } from "@/features/auth/services/signup-api";
import {
  getActiveLegalDocuments,
  type LegalDocumentMetadata,
} from "@/features/legal/services/legal-api";

const SIGNUP_ENABLED = process.env.NEXT_PUBLIC_KORDENA_SIGNUP_ENABLED === "true";

export default function SignupPage() {
  const [submitting, setSubmitting] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [legalDocuments, setLegalDocuments] = useState<LegalDocumentMetadata[]>([]);
  const [legalFailed, setLegalFailed] = useState(false);

  useEffect(() => {
    if (!SIGNUP_ENABLED) return;
    let cancelled = false;
    void getActiveLegalDocuments()
      .then((documents) => {
        if (!cancelled) {
          setLegalDocuments(documents);
          setLegalFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setLegalFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const terms = legalDocuments.find((document) => document.document_type === "terms");
  const privacy = legalDocuments.find((document) => document.document_type === "privacy");
  const dpa = legalDocuments.find((document) => document.document_type === "dpa");
  const legalReady = Boolean(terms && privacy && dpa);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!legalReady) {
      setError("Não foi possível validar a versão jurídica vigente. O cadastro permanece bloqueado.");
      return;
    }

    setSubmitting(true);
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
        legal_documents: Object.fromEntries(
          legalDocuments.map((document) => [
            document.document_type,
            { version: document.version, sha256: document.sha256 },
          ]),
        ),
        consents: { marketing: data.get("marketing") === "on" },
      });
      setAccepted(true);
    } catch (cause) {
      if (cause instanceof SignupApiError && cause.status === 429) {
        setError("Muitas tentativas. Aguarde alguns minutos e tente novamente.");
      } else if (cause instanceof SignupApiError && cause.status === 422) {
        setError("A versão jurídica mudou ou o aceite não pôde ser validado. Recarregue o cadastro.");
      } else {
        setError("Não foi possível iniciar o cadastro agora.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!SIGNUP_ENABLED) {
    return (
      <main className="kordena-page-dark relative flex min-h-screen items-center justify-center overflow-hidden px-5 text-white">
        <section className="kordena-panel-dark relative w-full max-w-lg rounded-[2rem] p-8 text-center">
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
      <main className="kordena-page-dark relative flex min-h-screen items-center justify-center overflow-hidden px-5 text-white">
        <section className="kordena-panel-dark relative w-full max-w-lg rounded-[2rem] p-8 text-center">
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
    <main className="kordena-page-dark relative min-h-screen overflow-hidden px-5 py-10 text-white">
      <section className="kordena-panel-dark relative mx-auto w-full max-w-xl rounded-[2rem] p-6 sm:p-8">
        <Link href="/login" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
          <ArrowLeft className="size-4" /> Voltar
        </Link>
        <h1 className="mt-6 text-3xl font-black">Começar teste grátis</h1>
        <p className="mt-2 text-sm leading-6 text-slate-400">
          Crie sua conta para iniciar o processo seguro de ativação do Kordena.
        </p>

        {legalFailed ? (
          <div role="alert" className="mt-5 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
            Não foi possível validar os documentos jurídicos oficiais. Por segurança, o cadastro está bloqueado.
          </div>
        ) : null}

        <form className="mt-7 space-y-4" onSubmit={(event) => void submit(event)}>
          <Input name="owner_name" aria-label="Nome do responsável" placeholder="Nome do responsável" required maxLength={255} />
          <Input name="email" aria-label="E-mail" type="email" placeholder="E-mail" required maxLength={320} />
          <Input name="phone" aria-label="Telefone ou WhatsApp" placeholder="Telefone ou WhatsApp" maxLength={64} />
          <Input name="password" aria-label="Senha" type="password" autoComplete="new-password" placeholder="Senha" required minLength={8} maxLength={1024} />
          <Input name="establishment_name" aria-label="Nome do estabelecimento" placeholder="Nome do estabelecimento" required maxLength={255} />
          <Input name="segment" aria-label="Segmento" placeholder="Segmento" required maxLength={96} />

          <div className="rounded-2xl border border-blue-400/15 bg-blue-400/[0.05] p-4">
            {legalReady ? (
              <label className="flex items-start gap-3 text-sm leading-6 text-slate-300">
                <input name="terms_accepted" type="checkbox" required className="mt-1.5" />
                <span>
                  Li e aceito os{" "}
                  <Link className="font-semibold text-blue-300 hover:text-blue-200" href="/legal/termos" target="_blank">
                    Termos de Uso v{terms?.version}
                  </Link>
                  , declaro ter lido a{" "}
                  <Link className="font-semibold text-blue-300 hover:text-blue-200" href="/legal/privacidade" target="_blank">
                    Política de Privacidade v{privacy?.version}
                  </Link>{" "}
                  e reconheço o{" "}
                  <Link className="font-semibold text-blue-300 hover:text-blue-200" href="/legal/dpa" target="_blank">
                    DPA v{dpa?.version}
                  </Link>{" "}
                  como parte aplicável da relação empresarial, quando cabível.
                </span>
              </label>
            ) : (
              <div className="flex items-center gap-3 text-sm text-slate-400">
                <Loader2 className="size-4 animate-spin text-blue-400" />
                Validando versões jurídicas vigentes…
              </div>
            )}
          </div>

          <label className="flex items-start gap-3 rounded-2xl border border-white/5 p-4 text-sm text-slate-400">
            <input name="marketing" type="checkbox" className="mt-1" />
            <span>
              Aceito receber comunicações comerciais opcionais. Esta escolha é independente do aceite necessário para criar a conta.
            </span>
          </label>

          {error ? <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/10 p-3 text-sm">{error}</div> : null}
          <Button type="submit" className="h-12 w-full" disabled={submitting || !legalReady}>
            {submitting ? <><Loader2 className="animate-spin" />Enviando…</> : "Continuar"}
          </Button>
        </form>
      </section>
    </main>
  );
}
