"use client";

import {
  AlertTriangle,
  BadgeCheck,
  CalendarDays,
  CircleDollarSign,
  CreditCard,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  getCommercialAccess,
  getCommercialPlans,
  getCommercialSubscription,
  startCommercialCheckout,
  type CommercialAccessStatus,
  type CommercialPaymentMethod,
  type CommercialPlan,
  type CommercialPlanPrice,
  type CommercialSubscription,
} from "@/features/commercial/services/commercial-access-api";

function formatMoney(currency: string, amount: string): string {
  try {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency,
    }).format(Number(amount));
  } catch {
    return `${currency} ${amount}`;
  }
}

function formatDate(value: string | null): string {
  if (!value) return "Não informado";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Não informado";
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(date);
}

function subscriptionStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "Pendente",
    active: "Ativa",
    past_due: "Pagamento pendente",
    suspended: "Suspensa",
    canceled: "Cancelada",
  };
  return labels[status] ?? status;
}

function accessModeLabel(mode: CommercialAccessStatus["access_mode"]): string {
  const labels: Record<string, string> = {
    full: "Acesso completo",
    limited: "Acesso limitado",
    billing_only: "Somente faturamento",
    blocked: "Bloqueado",
  };
  return mode ? labels[mode] ?? mode : "Não classificado";
}

function billingPeriodLabel(period: string): string {
  const labels: Record<string, string> = {
    monthly: "mês",
    month: "mês",
    mensal: "mês",
    yearly: "ano",
    annual: "ano",
    year: "ano",
    anual: "ano",
  };
  return labels[period] ?? period;
}

export function CommercialAccountWorkspace() {
  const auth = useAuthStore();
  const [access, setAccess] = useState<CommercialAccessStatus | null>(null);
  const [plans, setPlans] = useState<CommercialPlan[]>([]);
  const [subscription, setSubscription] = useState<CommercialSubscription | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<CommercialPaymentMethod>("pix");
  const [loading, setLoading] = useState(true);
  const [checkoutKey, setCheckoutKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [accessResult, plansResult, subscriptionResult] = await Promise.all([
        getCommercialAccess(),
        getCommercialPlans(),
        getCommercialSubscription(),
      ]);
      setAccess(accessResult);
      setPlans(plansResult);
      setSubscription(subscriptionResult.subscription);
    } catch {
      setAccess(null);
      setPlans([]);
      setSubscription(null);
      setError("Não foi possível carregar os dados comerciais da conta agora.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status !== "authenticated") return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [auth.status, auth.tenantId, load]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URL(window.location.href).searchParams;
      if (params.get("commercial_checkout") === "success") {
        setNotice("Checkout concluído no provedor. O status da assinatura será atualizado pela autoridade de billing.");
      } else if (params.get("commercial_checkout") === "cancel") {
        setNotice("Checkout cancelado. Nenhuma alteração comercial foi presumida pelo Kordena.");
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const currentPlan = useMemo(
    () => plans.find((plan) => plan.plan_code === subscription?.plan_code) ?? null,
    [plans, subscription],
  );

  const checkoutAllowed = Boolean(access && !access.operational_allowed);

  async function beginCheckout(plan: CommercialPlan, price: CommercialPlanPrice) {
    if (!checkoutAllowed || checkoutKey !== null) return;
    const key = `${plan.plan_code}:${price.price_id}`;
    setCheckoutKey(key);
    setError(null);
    setNotice(null);
    try {
      const result = await startCommercialCheckout({
        plan_code: plan.plan_code,
        plan_version_id: plan.plan_version_id,
        price_id: price.price_id,
        payment_method: paymentMethod,
      });
      window.location.assign(result.checkout_url);
    } catch {
      setError(
        "O checkout não pôde ser iniciado. O provedor de billing precisa estar configurado e disponível para esta conta.",
      );
    } finally {
      setCheckoutKey(null);
    }
  }

  if (loading) {
    return (
      <main className="kordena-page min-h-full px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
        <div className="mx-auto flex min-h-72 max-w-6xl items-center justify-center gap-3 rounded-3xl border border-slate-700/60 bg-slate-900/70 text-sm text-slate-300">
          <Loader2 className="size-5 animate-spin text-sky-300" />
          Carregando plano e assinatura…
        </div>
      </main>
    );
  }

  return (
    <main className="kordena-page min-h-full px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
      <div className="kordena-enter mx-auto w-full max-w-7xl space-y-6">
        <header className="relative overflow-hidden rounded-[2rem] border border-slate-700/60 bg-[linear-gradient(145deg,rgba(15,30,51,0.98),rgba(8,20,36,0.98))] p-6 shadow-[0_28px_76px_-40px_rgba(0,0,0,0.88)] sm:p-8">
          <div className="pointer-events-none absolute -right-20 -top-24 size-64 rounded-full bg-sky-500/10 blur-3xl" />
          <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-sky-300/20 bg-sky-400/[0.08] px-3 py-1.5 text-xs font-bold text-sky-200">
                <CreditCard className="size-3.5" />
                Conta comercial Kordena
              </div>
              <h1 className="mt-5 text-3xl font-black tracking-[-0.035em] text-slate-50 sm:text-4xl">
                Plano e Assinatura
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-400">
                Consulte entitlement, assinatura e ofertas do Kordena usando a mesma autoridade comercial que governa trial, paywall e billing.
              </p>
            </div>
            <Button variant="outline" onClick={() => void load()} disabled={checkoutKey !== null}>
              <RefreshCw className="size-4" />
              Atualizar
            </Button>
          </div>
        </header>

        {error ? (
          <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/[0.08] p-4 text-sm text-rose-100">
            <AlertTriangle className="mt-0.5 size-5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        {notice ? (
          <div role="status" className="rounded-2xl border border-sky-400/20 bg-sky-400/[0.08] p-4 text-sm text-sky-100">
            {notice}
          </div>
        ) : null}

        <section className="grid gap-4 md:grid-cols-3">
          <Metric
            icon={<ShieldCheck className="size-5" />}
            label="Acesso comercial"
            value={access?.operational_allowed ? "Liberado" : "Restrito"}
            detail={accessModeLabel(access?.access_mode ?? null)}
          />
          <Metric
            icon={<BadgeCheck className="size-5" />}
            label="Entitlement"
            value={access?.entitled ? "Válido" : "Não ativo"}
            detail={access?.reason ?? "Status indisponível"}
          />
          <Metric
            icon={<CreditCard className="size-5" />}
            label="Assinatura"
            value={subscription ? subscriptionStatusLabel(subscription.status) : "Não encontrada"}
            detail={subscription?.plan_code ?? "Nenhum plano contratado"}
          />
        </section>

        <section className="grid gap-6 xl:grid-cols-[0.9fr_1.6fr]">
          <article className="rounded-3xl border border-slate-700/60 bg-slate-900/70 p-6">
            <p className="text-xs font-black uppercase tracking-[0.18em] text-sky-300">
              Assinatura atual
            </p>
            {subscription ? (
              <div className="mt-5 space-y-5">
                <div>
                  <p className="text-2xl font-black text-white">
                    {currentPlan?.display_name ?? subscription.plan_code}
                  </p>
                  <p className="mt-1 text-sm text-slate-400">
                    {formatMoney(subscription.currency, subscription.contracted_amount)} / {billingPeriodLabel(subscription.billing_period)}
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Detail label="Status" value={subscriptionStatusLabel(subscription.status)} />
                  <Detail label="Plano" value={subscription.plan_code} mono />
                  <Detail label="Início do período" value={formatDate(subscription.current_period_start)} icon={<CalendarDays className="size-4" />} />
                  <Detail label="Fim do período" value={formatDate(subscription.current_period_end)} icon={<CalendarDays className="size-4" />} />
                </div>
                {subscription.cancel_at_period_end ? (
                  <p className="rounded-xl border border-amber-400/20 bg-amber-400/[0.08] p-3 text-sm text-amber-100">
                    O cancelamento ao fim do período já está registrado pela autoridade comercial.
                  </p>
                ) : null}
                <p className="text-xs leading-5 text-slate-500">
                  Alterações de estado dependem do Subscription/Billing canônico. Esta tela não inventa cancelamento, confirmação financeira ou ativação local.
                </p>
              </div>
            ) : (
              <div className="mt-5 rounded-2xl border border-slate-700/60 bg-slate-950/45 p-5 text-sm leading-6 text-slate-400">
                Nenhuma assinatura foi encontrada para a conta de produto deste tenant. O catálogo abaixo continua sendo lido da autoridade comercial.
              </div>
            )}
          </article>

          <article className="rounded-3xl border border-slate-700/60 bg-slate-900/70 p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.18em] text-sky-300">
                  Catálogo comercial
                </p>
                <h2 className="mt-2 text-2xl font-black text-white">Planos disponíveis</h2>
                <p className="mt-2 text-sm text-slate-400">
                  Nomes, preços e versões vêm do catálogo versionado; nenhum valor comercial é hardcoded nesta tela.
                </p>
              </div>
              <label className="text-xs font-semibold text-slate-400">
                Forma de pagamento
                <select
                  className="mt-1 block h-10 rounded-xl border border-slate-700 bg-slate-950 px-3 text-sm text-white"
                  value={paymentMethod}
                  onChange={(event) => setPaymentMethod(event.target.value as CommercialPaymentMethod)}
                  disabled={!checkoutAllowed}
                >
                  <option value="pix">Pix</option>
                  <option value="card">Cartão</option>
                  <option value="boleto">Boleto</option>
                  <option value="bank_transfer">Transferência bancária</option>
                </select>
              </label>
            </div>

            {!checkoutAllowed ? (
              <p className="mt-5 rounded-xl border border-emerald-400/20 bg-emerald-400/[0.07] p-3 text-sm text-emerald-100">
                O acesso operacional está liberado. Para evitar duplicidade de assinatura, esta superfície mantém o checkout bloqueado enquanto o entitlement atual estiver válido.
              </p>
            ) : null}

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              {plans.map((plan) => (
                <article
                  key={plan.plan_code}
                  className={[
                    "rounded-2xl border p-5",
                    plan.plan_code === subscription?.plan_code
                      ? "border-sky-400/30 bg-sky-400/[0.07]"
                      : "border-slate-700/60 bg-slate-950/45",
                  ].join(" ")}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.16em] text-sky-300">
                        {plan.marketing_badge ?? plan.plan_code}
                      </p>
                      <h3 className="mt-2 text-lg font-black text-white">{plan.display_name}</h3>
                    </div>
                    {plan.plan_code === subscription?.plan_code ? (
                      <span className="rounded-full border border-sky-300/20 bg-sky-300/[0.08] px-2.5 py-1 text-[10px] font-black text-sky-100">
                        Plano atual
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-2 min-h-10 text-sm leading-5 text-slate-400">
                    {plan.description ?? "Plano comercial Kordena."}
                  </p>
                  <div className="mt-4 space-y-3">
                    {plan.prices.map((price) => {
                      const key = `${plan.plan_code}:${price.price_id}`;
                      const busy = checkoutKey === key;
                      return (
                        <div key={price.price_id} className="rounded-xl border border-slate-700/60 bg-slate-950/55 p-3">
                          <div className="flex items-center gap-2">
                            <CircleDollarSign className="size-4 text-emerald-300" />
                            <span className="font-bold text-white">
                              {formatMoney(price.currency, price.amount)}
                            </span>
                            <span className="text-xs text-slate-500">/{billingPeriodLabel(price.billing_period)}</span>
                          </div>
                          {checkoutAllowed ? (
                            <Button
                              type="button"
                              className="mt-3 w-full"
                              disabled={checkoutKey !== null}
                              onClick={() => void beginCheckout(plan, price)}
                            >
                              {busy ? <Loader2 className="size-4 animate-spin" /> : <CreditCard className="size-4" />}
                              {busy ? "Abrindo checkout…" : "Contratar este plano"}
                            </Button>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </article>
              ))}
            </div>

            {plans.length === 0 ? (
              <p className="mt-5 rounded-xl border border-amber-400/20 bg-amber-400/[0.08] p-4 text-sm text-amber-100">
                Nenhuma oferta comercial publicada está disponível neste momento.
              </p>
            ) : null}
          </article>
        </section>
      </div>
    </main>
  );
}

function Metric({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900/70 p-5">
      <div className="flex items-center gap-2 text-sky-300">{icon}</div>
      <p className="mt-4 text-xs font-bold uppercase tracking-[0.15em] text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-black text-white">{value}</p>
      <p className="mt-1 truncate text-xs text-slate-500">{detail}</p>
    </div>
  );
}

function Detail({
  label,
  value,
  mono = false,
  icon,
}: {
  label: string;
  value: string;
  mono?: boolean;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-950/45 p-3">
      <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500">
        {icon}
        {label}
      </p>
      <p className={`mt-2 text-sm font-semibold text-slate-100 ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}
