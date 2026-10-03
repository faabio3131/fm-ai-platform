import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { MetricService } from "@/application/metrics/metric-service";
import { OperationalHealthService } from "@/application/operations/operational-health-service";
import { OperationsIntelligenceService } from "@/application/operations/operations-intelligence-service";
import { resolveTenantContext } from "@/application/security/resolve-tenant-context";
import { AuthenticationRequiredError, TenantScopeRequiredError } from "@/domain/security/tenant-context";
import { PostgresMetricStore } from "@/infrastructure/metrics/postgres-metric-store";
import { PostgresOperationalHealthRepository } from "@/infrastructure/operations/postgres-health-repository";
import { PostgresProductRepository } from "@/infrastructure/products/postgres-product-repository";

function statusLabel(status: "operational" | "degraded" | "unavailable" | "unknown") {
  if (status === "operational") return "Operacional";
  if (status === "degraded") return "Degradado";
  if (status === "unavailable") return "Indisponível";
  return "Desconhecido";
}

export default async function OperationsPage() {
  let context;
  try {
    context = await resolveTenantContext(await headers());
  } catch (error) {
    if (error instanceof AuthenticationRequiredError) redirect("/sign-in");
    if (error instanceof TenantScopeRequiredError) redirect("/onboarding");
    throw error;
  }

  const products = new PostgresProductRepository();
  const [overview, health] = await Promise.all([
    new OperationsIntelligenceService(
      new MetricService(new PostgresMetricStore()),
      products,
    ).overview(context),
    new OperationalHealthService(
      new PostgresOperationalHealthRepository(),
      products,
    ).overview(context),
  ]);

  const hasMonitoredServices = health.services.length > 0;

  return (
    <main className="dashboard-shell">
      <header className="dashboard-header">
        <div>
          <span className="eyebrow">F14 · Operações, SRE e Incidentes</span>
          <h1>Saúde operacional governada</h1>
          <p>
            Health pontual não é uptime. Disponibilidade só aparece quando houver
            série temporal governada.
          </p>
        </div>
        <Link href="/dashboard">Voltar</Link>
      </header>

      <section className="metric-grid" aria-label="Resumo da saúde operacional">
        <article className="metric-card">
          <span className="metric-label">Serviços monitorados</span>
          <strong>{hasMonitoredServices ? health.services.length : "Indisponível"}</strong>
          <small>{hasMonitoredServices ? "Autoridades de saúde registradas" : "Nenhuma autoridade de saúde registrada"}</small>
        </article>
        <article className="metric-card">
          <span className="metric-label">Operacionais</span>
          <strong>{hasMonitoredServices ? health.counts.operational : "Indisponível"}</strong>
          <small>Observações atuais e não stale</small>
        </article>
        <article className="metric-card">
          <span className="metric-label">Degradados</span>
          <strong>{hasMonitoredServices ? health.counts.degraded : "Indisponível"}</strong>
          <small>Estado reportado por fonte governada</small>
        </article>
        <article className="metric-card">
          <span className="metric-label">Indisponíveis / desconhecidos</span>
          <strong>
            {hasMonitoredServices
              ? health.counts.unavailable + health.counts.unknown
              : "Indisponível"}
          </strong>
          <small>Stale é tratado como desconhecido, nunca como saudável</small>
        </article>
      </section>

      <section className="panel" aria-labelledby="service-health-title">
        <h2 id="service-health-title">Status dos Serviços</h2>
        <p>{health.availability.reason}</p>
        {health.services.length ? (
          <div className="foundation-grid">
            {health.services.map(({ service, observation, effectiveStatus }) => (
              <article key={service.id}>
                <strong>{service.name}</strong>
                <span>{service.environment} · {statusLabel(effectiveStatus)}</span>
                <small>
                  {observation
                    ? `Fonte: ${observation.sourceAuthority} · ${observation.freshnessStatus} · ${observation.observedAt.toISOString()}`
                    : "Sem observação governada"}
                </small>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <strong>Nenhum serviço monitorado.</strong>
            <p>
              Registre uma autoridade de saúde antes de reportar disponibilidade.
              O FM Command não converte ausência de observação em estado saudável.
            </p>
          </div>
        )}
      </section>

      <section className="metric-grid">
        {overview.metrics.map(({ target, status, value }) => (
          <article className="metric-card" key={target.metricId}>
            <span className="metric-label">{target.displayName}</span>
            <strong>
              {status === "pending_semantics"
                ? "Semântica pendente"
                : value?.value ?? "Indisponível"}
            </strong>
            <small>
              {value
                ? `Fonte: ${value.sourceAuthority}`
                : status === "pending_semantics"
                  ? "Regra ainda não aprovada"
                  : "Telemetria ainda não conectada"}
            </small>
          </article>
        ))}
      </section>

      <section className="panel" aria-labelledby="platform-health-title">
        <h2 id="platform-health-title">Saúde técnica da plataforma</h2>
        <p>
          Diagnósticos de infraestrutura pertencem ao FM Command. Clientes dos
          produtos não precisam visualizar detalhes de backend, contratos de health
          ou fronteiras técnicas da plataforma.
        </p>
        <div className="foundation-grid">
          <article>
            <strong>Health contract</strong>
            <span><code>{overview.runtime.healthEndpoint}</code></span>
            <small>Saúde pontual do runtime do FM Command.</small>
          </article>
          <article>
            <strong>Readiness contract</strong>
            <span><code>{overview.runtime.readinessEndpoint}</code></span>
            <small>Prontidão técnica para receber tráfego.</small>
          </article>
          <article>
            <strong>Segurança</strong>
            <span>Escopo governado por organização e papel</span>
            <small>Diagnóstico técnico restrito ao ambiente administrativo da FM Tecnologia.</small>
          </article>
        </div>
        <p>{overview.availability.reason}</p>
      </section>

      <section className="panel">
        <h2>Sinais operacionais</h2>
        <p>{overview.alerts.reason}</p>
      </section>
    </main>
  );
}
