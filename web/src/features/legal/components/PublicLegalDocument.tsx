"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, FileText, Loader2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  getLegalDocument,
  type LegalDocumentDetail,
  type LegalDocumentType,
} from "@/features/legal/services/legal-api";

const TITLES: Record<LegalDocumentType, string> = {
  terms: "Termos de Uso",
  privacy: "Política de Privacidade e LGPD",
  dpa: "Anexo de Tratamento de Dados (DPA)",
};

export function PublicLegalDocument({
  documentType,
}: {
  documentType: LegalDocumentType;
}) {
  const [document, setDocument] = useState<LegalDocumentDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getLegalDocument(documentType)
      .then((payload) => {
        if (!cancelled) {
          setDocument(payload);
          setFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [documentType]);

  if (failed) {
    return (
      <main className="kordena-page-dark flex min-h-screen items-center justify-center px-5 text-white">
        <section className="kordena-panel-dark w-full max-w-xl rounded-[2rem] p-8 text-center">
          <ShieldCheck className="mx-auto size-10 text-amber-300" />
          <h1 className="mt-5 text-2xl font-black">Documento temporariamente indisponível</h1>
          <p className="mt-3 text-sm leading-6 text-slate-400">
            O cadastro permanece bloqueado até que a versão jurídica oficial possa ser validada.
          </p>
          <Button asChild className="mt-6">
            <Link href="/signup"><ArrowLeft />Voltar ao cadastro</Link>
          </Button>
        </section>
      </main>
    );
  }

  if (!document) {
    return (
      <main className="kordena-page-dark flex min-h-screen items-center justify-center text-white">
        <div className="flex items-center gap-3 text-sm text-slate-300">
          <Loader2 className="size-5 animate-spin text-blue-400" />
          Carregando documento oficial…
        </div>
      </main>
    );
  }

  return (
    <main className="kordena-page-dark min-h-screen px-5 py-10 text-white">
      <section className="kordena-panel-dark mx-auto w-full max-w-4xl rounded-[2rem] p-6 sm:p-9">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/10 pb-5">
          <div>
            <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-blue-300">
              <FileText className="size-4" />
              Documento jurídico oficial
            </div>
            <h1 className="mt-3 text-2xl font-black sm:text-3xl">{TITLES[documentType]}</h1>
            <p className="mt-2 text-sm text-slate-400">
              Versão {document.version} · vigência {new Date(document.effective_at).toLocaleDateString("pt-BR")}
            </p>
          </div>
          <Button asChild variant="outline">
            <Link href="/signup"><ArrowLeft />Cadastro</Link>
          </Button>
        </div>
        <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/50 p-5">
          <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-7 text-slate-300">
            {document.content}
          </pre>
        </div>
        <p className="mt-5 break-all text-xs text-slate-500">
          SHA-256: {document.sha256}
        </p>
      </section>
    </main>
  );
}
