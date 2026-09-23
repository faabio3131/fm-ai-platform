"use client";

import { CreditCard, Loader2, LogOut, RefreshCw, ShieldAlert } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  getCommercialAccess,
  getCommercialPlans,
  type CommercialAccessStatus,
  type CommercialPlan,
} from "@/features/commercial/services/commercial-access-api";
import { endAuthSession, useAuthStore } from "@/features/auth/store/auth-store";

const EXEMPT_PATHS = ["/login", "/signup", "/cardapio"] as const;

function isProtectedPath(pathname: string): boolean {
  return !EXEMPT_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  );
}

export function CommercialAccessGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const auth = useAuthStore();
  const protectedPath = isProtectedPath(pathname);
  const [access, setAccess] = useState<CommercialAccessStatus | null>(null);
  const [plans, setPlans] = useState<CommercialPlan[]>([]);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    if (!protectedPath || auth.status !== "authenticated") {
      return;
    }
    setLoading(true);
    setFailed(false);
    try {
      const status = await getCommercialAccess();
      setAccess(status);
      if (!status.operational_allowed) {
        setPlans(await getCommercialPlans());
      } else {
        setPlans([]);
      }
    } catch {
      setFailed(true);
      setAccess(null);
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, [auth.status, protectedPath]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load, auth.tenantId]);

  if (!protectedPath || auth.status !== "authenticated") {
    return children;
  }

  if (loading || access === null) {
    if (failed) {
      return (
        <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-white">
          <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
            <ShieldAlert className="mb-4 size-8 text-amber-400" />
            <h1 className="text-lg font-semibold">Não foi possível validar o acesso comercial</h1>
            <p className="mt-2 text-sm leading-6 text-slate-400">
              Os módulos operacionais permanecem bloqueados até o servidor confirmar o entitlement da conta.
            </p>
            <div className="mt-5 flex gap-3">
              <Button className="flex-1" onClick={() => void load()}>
                <RefreshCw className="size-4" />
                Tentar novamente
              </Button>
              <Button
                variant="outline"
                onClick={() =>
                  void endAuthSession().finally(() => router.replace("/login"))
                }
              >
                <LogOut className="size-4" />
                Sair
              </Button>
            </div>
          </div>
        </main>
      );
    }
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        <div className="flex items-center gap-3 text-sm">
          <Loader2 className="size-5 animate-spin text-blue-400" />
          Validando acesso comercial…
        </div>
      </main>
    );
  }

  if (access.operational_allowed) {
    return children;
  }

  return (
    <main className="min-h-screen bg-slate-950 px-5 py-10 text-white">
      <section className="mx-auto max-w-6xl">
        <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-6 shadow-2xl md:p-9">
          <div className="flex items-start justify-between gap-5">
            <div>
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-400/20 bg-blue-400/10 px-3 py-1 text-xs font-medium text-blue-200">
                <CreditCard className="size-3.5" />
                Acesso comercial
              </div>
              <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
                Seu acesso operacional está pausado
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400 md:text-base">
                Seus dados permanecem preservados. Escolha um plano disponível para continuar o processo de assinatura e restaurar o acesso.
              </p>
            </div>
            <Button
              variant="outline"
              onClick={() =>
                void endAuthSession().finally(() => router.replace("/login"))
              }
            >
              <LogOut className="size-4" />
              Sair
            </Button>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => (
              <article
                key={plan.plan_code}
                className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5"
              >
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-blue-300">
                  {plan.marketing_badge ?? plan.plan_code}
                </p>
                <h2 className="mt-2 text-lg font-semibold">{plan.display_name}</h2>
                <p className="mt-2 min-h-12 text-sm leading-5 text-slate-400">
                  {plan.description ?? "Plano comercial Kordena."}
                </p>
                <div className="mt-5 space-y-2">
                  {plan.prices.map((price) => (
                    <div key={price.price_id}>
                      <span className="text-xl font-semibold">
                        {price.currency} {price.amount}
                      </span>
                      <span className="ml-1 text-xs text-slate-500">
                        /{price.billing_period}
                      </span>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>

          {plans.length === 0 ? (
            <p className="mt-8 rounded-xl border border-amber-400/20 bg-amber-400/10 p-4 text-sm text-amber-100">
              Nenhuma oferta comercial publicada está disponível neste momento. O acesso continua protegido e seus dados permanecem preservados.
            </p>
          ) : null}
        </div>
      </section>
    </main>
  );
}
