"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  SignupApiError,
  verifySignupEmail,
} from "@/features/auth/services/signup-api";

const SIGNUP_ENABLED = process.env.NEXT_PUBLIC_KORDENA_SIGNUP_ENABLED === "true";

type VerificationState = "verifying" | "ready" | "error" | "disabled";

export default function SignupVerifyPage() {
  const [state, setState] = useState<VerificationState>(
    SIGNUP_ENABLED ? "verifying" : "disabled",
  );

  useEffect(() => {
    if (!SIGNUP_ENABLED) {
      return;
    }
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const signupId = params.get("signup_id") ?? "";
    const token = params.get("token") ?? "";
    if (!signupId || !token) {
      setState("error");
      return;
    }
    window.history.replaceState({}, "", "/signup/verify");
    void verifySignupEmail(signupId, token)
      .then((result) => {
        setState(result.ready ? "ready" : "error");
      })
      .catch((error: unknown) => {
        if (error instanceof SignupApiError) {
          setState("error");
          return;
        }
        setState("error");
      });
  }, []);

  if (state === "verifying") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#06101d] px-5 text-white">
        <section className="w-full max-w-lg rounded-[2rem] border border-white/[0.09] bg-slate-900/80 p-8 text-center">
          <Loader2 className="mx-auto size-10 animate-spin text-blue-300" />
          <h1 className="mt-5 text-2xl font-black">Confirmando seu e-mail</h1>
          <p className="mt-3 text-sm text-slate-400">
            Validando o link e preparando sua conta Kordena.
          </p>
        </section>
      </main>
    );
  }

  if (state === "ready") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#06101d] px-5 text-white">
        <section className="w-full max-w-lg rounded-[2rem] border border-white/[0.09] bg-slate-900/80 p-8 text-center">
          <CheckCircle2 className="mx-auto size-10 text-emerald-300" />
          <h1 className="mt-5 text-2xl font-black">E-mail confirmado</h1>
          <p className="mt-3 text-sm text-slate-400">
            Sua conta foi provisionada e está pronta para entrar.
          </p>
          <Button asChild className="mt-6">
            <Link href="/login">Entrar no Kordena</Link>
          </Button>
        </section>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#06101d] px-5 text-white">
      <section className="w-full max-w-lg rounded-[2rem] border border-white/[0.09] bg-slate-900/80 p-8 text-center">
        <ShieldAlert className="mx-auto size-10 text-amber-300" />
        <h1 className="mt-5 text-2xl font-black">
          {state === "disabled" ? "Verificação não liberada" : "Link inválido ou expirado"}
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-400">
          {state === "disabled"
            ? "O cadastro público continua fechado até a liberação controlada."
            : "Solicite um novo e-mail de verificação pelo fluxo de cadastro."}
        </p>
        <Button asChild className="mt-6">
          <Link href="/signup">Voltar ao cadastro</Link>
        </Button>
      </section>
    </main>
  );
}
