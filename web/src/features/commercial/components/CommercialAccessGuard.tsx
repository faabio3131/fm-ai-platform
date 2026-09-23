"use client";

import { CreditCard, LifeBuoy, Loader2, LogOut, RefreshCw, ShieldAlert } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  getCommercialAccess,
  getCommercialPlans,
  startCommercialCheckout,
  type CommercialAccessStatus,
  type CommercialPaymentMethod,
  type CommercialPlan,
  type CommercialPlanPrice,
} from "@/features/commercial/services/commercial-access-api";
import { endAuthSession, useAuthStore } from "@/features/auth/store/auth-store";

const EXEMPT_PATHS = ["/login", "/signup", "/cardapio"] as const;
const SUPPORT_URL = process.env.NEXT_PUBLIC_SUPPORT_URL?.trim() || null;

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
  const [paymentMethod, setPaymentMethod] = useState<CommercialPaymentMethod>("pix");
  const [checkoutKey, setCheckoutKey] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

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

  const beginCheckout = useCallback(
    async (plan: CommercialPlan, price: CommercialPlanPrice) => {
      const key = `${plan.plan_code}:${price.price_id}`;
      setCheckoutKey(key);
      setCheckoutError(null);
      try {
        const result = await startCommercialCheckout({
          plan_code: plan.plan_code,
          plan_version_id: plan.plan_version_id,
          price_id: price.price_id,
          payment_method: paymentMethod,
        });
        window.location.assign(result.checkout_url);
      } catch {
        setCheckoutError(
          "Não foi possível iniciar o checkout. Tente novamente ou use o canal de suporte.",
        );
      } finally {
        setCheckoutKey(null);
      }
    },
    [paymentMethod],
  );

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

          <div className="mt-7 flex flex-wrap items-center gap-3 rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
            <label htmlFor="commercial-payment-method" className="text-sm text-slate-300">
              Forma de pagamento
            </label>
            <select
              id="commercial-payment-method"
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
              value={paymentMethod}
              onChange={(event) =>
                setPaymentMethod(event.target.value as CommercialPaymentMethod)
              }
            >
              <option value="pix">Pix</option>
              <option value="card">Cartão</option>
              <option value="boleto">Boleto</option>
              <option value="bank_transfer">Transferência bancária</option>
            </select>
            {SUPPORT_URL ? (
              <a
                href={SUPPORT_URL}
                target="_blank"
                rel="noreferrer"
                className="ml-auto inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
              >
                <LifeBuoy className="size-4" />
                Falar com suporte
              </a>
            ) : (
              <span className="ml-auto text-xs text-slate-500">
                Canal de suporte não configurado neste ambiente.
              </span>
            )}
          </div>

          {checkoutError ? (
            <p
              role="alert"
              className="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100"
            >
              {checkoutError}
            </p>
          ) : null}

          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
                  {plan.prices.map((price) => {
                    const key = `${plan.plan_code}:${price.price_id}`;
                    const checkingOut = checkoutKey === key;
                    return (
                      <div
                        key={price.price_id}
                        className="rounded-xl border border-slate-800 p-3"
                      >
                        <div>
                          <span className="text-xl font-semibold">
                            {price.currency} {price.amount}
                          </span>
                          <span className="ml-1 text-xs text-slate-500">
                            /{price.billing_period}
                          </span>
                        </div>
                        <Button
                          className="mt-3 w-full"
                          disabled={checkoutKey !== null}
                          onClick={() => void beginCheckout(plan, price)}
                        >
                          {checkingOut ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <CreditCard className="size-4" />
                          )}
                          {checkingOut ? "Abrindo checkout…" : "Escolher este plano"}
                        </Button>
                      </div>
                    );
                  })}
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
