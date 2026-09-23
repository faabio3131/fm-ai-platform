"""KCA-13 — observabilidade comercial, antiabuso e FinOps governados.

Esta projeção é deliberadamente read-only. Ela deriva métricas exclusivamente de
fontes autoritativas já existentes e nunca transforma ausência de fonte em zero.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.ai_finops_models import AIFinOpsDailyORM
from infra.comercial.billing_events_orm import (
    FMBillingTransactionORM,
    FMBillingWebhookInboxORM,
)
from infra.comercial.entitlement_orm import KordenaEntitlementProjectionORM
from infra.comercial.modelos_orm import (
    CommercialAuditORM,
    CommercialOutboxORM,
    FMCustomerORM,
    FMProductAccountORM,
)
from infra.comercial.provisioning_orm import FMCommercialProvisioningSagaORM
from infra.comercial.signup_orm import FMPublicSignupIntentORM
from infra.comercial.subscription_orm import FMCommercialSubscriptionORM
from infra.comercial.trial_orm import FMCommercialTrialORM

SessionFactory = Callable[[], Session]

SCHEMA_VERSION = "kordena.observability.kca13.v1"
WINDOW_DAYS = 30
TRIAL_EXPIRING_DAYS = 7

_MONTHLY_PERIODS = frozenset({"MONTH", "MONTHLY", "MENSAL"})
_ANNUAL_PERIODS = frozenset({"YEAR", "YEARLY", "ANNUAL", "ANNUALLY"})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat()


def _metric(
    *,
    metric_id: str,
    status: str,
    value: Any,
    unit: str,
    as_of: datetime,
    provenance: tuple[str, ...],
    quality: str = "verified",
    definition: str,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "status": status,
        "value": value,
        "unit": unit,
        "as_of": _iso(as_of),
        "quality_status": quality,
        "source_authority": "fm_commercial_platform",
        "provenance_refs": list(provenance),
        "definition": definition,
    }


def _money_by_currency(rows: dict[str, Decimal]) -> list[dict[str, str]]:
    return [
        {"currency": currency, "amount": str(amount.quantize(Decimal("0.01")))}
        for currency, amount in sorted(rows.items())
    ]


class AplicacaoCommercialObservabilityKCA13:
    """Materializa telemetria comercial confiável sem criar nova autoridade."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def snapshot(self, *, agora: datetime | None = None) -> dict[str, Any]:
        now = _utc(agora or datetime.now(timezone.utc))
        window_start = now - timedelta(days=WINDOW_DAYS)
        expiring_until = now + timedelta(days=TRIAL_EXPIRING_DAYS)

        with self._session_factory() as session:
            customers = tuple(
                session.scalars(
                    select(FMCustomerORM).where(
                        FMCustomerORM.account_class != "internal_test"
                    )
                ).all()
            )
            customer_ids = {row.fm_customer_id for row in customers}
            accounts = tuple(
                session.scalars(
                    select(FMProductAccountORM).where(
                        FMProductAccountORM.product_code == "KORDENA",
                        FMProductAccountORM.fm_customer_id.in_(customer_ids),
                    )
                ).all()
            ) if customer_ids else ()
            account_ids = {row.product_account_id for row in accounts}
            tenant_ids = {
                row.product_tenant_id
                for row in accounts
                if row.product_tenant_id is not None
            }

            signups = tuple(
                session.scalars(
                    select(FMPublicSignupIntentORM).where(
                        FMPublicSignupIntentORM.created_at >= window_start,
                        FMPublicSignupIntentORM.created_at <= now,
                    )
                ).all()
            )
            provisioning = tuple(
                session.scalars(
                    select(FMCommercialProvisioningSagaORM).where(
                        FMCommercialProvisioningSagaORM.updated_at >= window_start,
                        FMCommercialProvisioningSagaORM.updated_at <= now,
                    )
                ).all()
            )
            trials = tuple(
                session.scalars(
                    select(FMCommercialTrialORM).where(
                        FMCommercialTrialORM.product_account_id.in_(account_ids)
                    )
                ).all()
            ) if account_ids else ()
            subscriptions = tuple(
                session.scalars(
                    select(FMCommercialSubscriptionORM).where(
                        FMCommercialSubscriptionORM.product_account_id.in_(account_ids)
                    )
                ).all()
            ) if account_ids else ()
            subscription_ids = {row.subscription_id for row in subscriptions}
            transactions = tuple(
                session.scalars(
                    select(FMBillingTransactionORM).where(
                        FMBillingTransactionORM.subscription_id.in_(subscription_ids)
                    )
                ).all()
            ) if subscription_ids else ()
            entitlements = tuple(
                session.scalars(
                    select(KordenaEntitlementProjectionORM).where(
                        KordenaEntitlementProjectionORM.tenant_id.in_(tenant_ids)
                    )
                ).all()
            ) if tenant_ids else ()
            webhooks = tuple(
                session.scalars(
                    select(FMBillingWebhookInboxORM).where(
                        FMBillingWebhookInboxORM.received_at >= window_start,
                        FMBillingWebhookInboxORM.received_at <= now,
                    )
                ).all()
            )
            audits = tuple(
                session.scalars(
                    select(CommercialAuditORM).where(
                        CommercialAuditORM.timestamp >= window_start,
                        CommercialAuditORM.timestamp <= now,
                    )
                ).all()
            )
            subscription_events = tuple(
                session.scalars(
                    select(CommercialOutboxORM).where(
                        CommercialOutboxORM.aggregate_type == "subscription",
                        CommercialOutboxORM.product_account_id.in_(account_ids),
                        CommercialOutboxORM.occurred_at <= now,
                    )
                ).all()
            ) if account_ids else ()
            finops = tuple(
                session.scalars(
                    select(AIFinOpsDailyORM).where(
                        AIFinOpsDailyORM.tenant_id.in_(tenant_ids),
                        AIFinOpsDailyORM.bucket_date >= window_start.date(),
                        AIFinOpsDailyORM.bucket_date <= now.date(),
                    )
                ).all()
            ) if tenant_ids else ()

        metrics = self._metrics(
            now=now,
            window_start=window_start,
            expiring_until=expiring_until,
            signups=signups,
            provisioning=provisioning,
            trials=trials,
            subscriptions=subscriptions,
            transactions=transactions,
            subscription_events=subscription_events,
            customer_ids=customer_ids,
        )
        finops_snapshot = self._finops(
            now=now,
            rows=finops,
            entitlements=entitlements,
        )
        antiabuse = self._antiabuse(
            now=now,
            signups=signups,
            provisioning=provisioning,
            trials=trials,
            audits=audits,
        )
        health = self._health(
            now=now,
            provisioning=provisioning,
            entitlements=entitlements,
            webhooks=webhooks,
            finops=finops_snapshot,
        )
        alerts = self._alerts(antiabuse=antiabuse, health=health)
        correlations = self._correlations(
            audits=audits,
            provisioning=provisioning,
            webhooks=webhooks,
        )

        return {
            "schema_version": SCHEMA_VERSION,
            "as_of": _iso(now),
            "window": {
                "days": WINDOW_DAYS,
                "start": _iso(window_start),
                "end": _iso(now),
            },
            "internal_test_excluded": True,
            "metrics": metrics,
            "antiabuse": antiabuse,
            "health": health,
            "finops": finops_snapshot,
            "alerts": alerts,
            "tracing": {
                "correlation_ids": correlations,
                "correlation_id_required_by_commercial_flows": True,
            },
            "coverage": {
                "commercial_metrics": "governed_existing_authorities",
                "signup_rate": "observed_raw_signal_no_risk_score",
                "trial_reuse": "historical_customer_trial_count",
                "admin_override": "commercial_audit_metadata",
                "ai_cost": "existing_ai_finops_read_model",
                "infrastructure_cost": "unavailable_source_not_configured",
                "churn": "event_reconstructed_logo_churn_30d",
                "fx": "not_applied_multi_currency_kept_separate",
            },
        }

    @staticmethod
    def _metrics(
        *,
        now: datetime,
        window_start: datetime,
        expiring_until: datetime,
        signups,
        provisioning,
        trials,
        subscriptions,
        transactions,
        subscription_events,
        customer_ids: set[str],
    ) -> dict[str, Any]:
        provenance_signup = ("table:fm_public_signup_intents_v1",)
        provenance_provisioning = ("table:fm_commercial_provisioning_sagas_v1",)
        provenance_trial = (
            "table:fm_commercial_trials_v1",
            "table:fm_customers_v1",
        )
        provenance_subscription = (
            "table:fm_commercial_subscriptions_v1",
            "table:fm_customers_v1",
        )
        provenance_billing = (
            "table:fm_billing_transactions_v1",
            "table:fm_commercial_subscriptions_v1",
            "table:fm_customers_v1",
        )

        signup_started = len(signups)
        signup_completed = sum(
            row.status == "ready"
            and _utc(row.updated_at) >= window_start
            and _utc(row.updated_at) <= now
            for row in signups
        )
        tenant_provisioned = sum(
            row.status == "ready"
            and row.fm_customer_id in customer_ids
            and _utc(row.updated_at) >= window_start
            and _utc(row.updated_at) <= now
            for row in provisioning
        )
        trials_started = [
            row for row in trials
            if row.started_at is not None
            and window_start <= _utc(row.started_at) <= now
        ]
        trial_started = len(trials_started)
        trial_active = sum(
            row.status == "active"
            and row.ends_at is not None
            and _utc(row.ends_at) > now
            for row in trials
        )
        trial_expiring = sum(
            row.status == "active"
            and row.ends_at is not None
            and now < _utc(row.ends_at) <= expiring_until
            for row in trials
        )
        trial_expired = sum(
            row.status == "expired"
            and window_start <= _utc(row.updated_at) <= now
            for row in trials
        )
        trial_converted = sum(
            row.converted_at is not None
            and window_start <= _utc(row.converted_at) <= now
            for row in trials
        )
        cohort_converted = sum(
            row.converted_at is not None and _utc(row.converted_at) <= now
            for row in trials_started
        )
        conversion_rate = (
            Decimal(cohort_converted) * Decimal(100) / Decimal(trial_started)
            if trial_started
            else None
        )

        subscription_active = sum(row.status == "active" for row in subscriptions)
        past_due = sum(row.status == "past_due" for row in subscriptions)

        payment_success = sum(
            row.transaction_type == "payment"
            and row.status == "succeeded"
            and window_start
            <= _utc(row.provider_occurred_at or row.updated_at)
            <= now
            for row in transactions
        )
        payment_failure = sum(
            row.transaction_type == "payment"
            and row.status == "failed"
            and window_start
            <= _utc(row.provider_occurred_at or row.updated_at)
            <= now
            for row in transactions
        )

        mrr: dict[str, Decimal] = defaultdict(Decimal)
        arr: dict[str, Decimal] = defaultdict(Decimal)
        unsupported_periods: Counter[str] = Counter()
        for row in subscriptions:
            if row.status != "active":
                continue
            period = row.billing_period.strip().upper()
            currency = row.currency.strip().upper()
            amount = Decimal(row.contracted_amount)
            if period in _MONTHLY_PERIODS:
                mrr[currency] += amount
                arr[currency] += amount * Decimal(12)
            elif period in _ANNUAL_PERIODS:
                mrr[currency] += amount / Decimal(12)
                arr[currency] += amount
            else:
                unsupported_periods[period or "EMPTY"] += 1

        churn = AplicacaoCommercialObservabilityKCA13._churn(
            now=now,
            window_start=window_start,
            subscription_events=subscription_events,
        )

        money_quality = "partial" if unsupported_periods else "verified"
        money_status = "partial" if unsupported_periods else "available"

        return {
            "signup_started": _metric(
                metric_id="signup_started",
                status="available",
                value=signup_started,
                unit="count",
                as_of=now,
                provenance=provenance_signup,
                definition="Public signup intents created in the rolling 30-day window.",
            ),
            "signup_completed": _metric(
                metric_id="signup_completed",
                status="available",
                value=signup_completed,
                unit="count",
                as_of=now,
                provenance=provenance_signup,
                definition="Public signup intents that reached READY during the rolling 30-day window.",
            ),
            "tenant_provisioned": _metric(
                metric_id="tenant_provisioned",
                status="available",
                value=tenant_provisioned,
                unit="count",
                as_of=now,
                provenance=provenance_provisioning,
                definition="Provisioning sagas that reached READY with a customer binding during the rolling 30-day window.",
            ),
            "trial_started": _metric(
                metric_id="trial_started",
                status="available",
                value=trial_started,
                unit="count",
                as_of=now,
                provenance=provenance_trial,
                definition="Non-INTERNAL_TEST trials started during the rolling 30-day window.",
            ),
            "trial_active": _metric(
                metric_id="trial_active",
                status="available",
                value=trial_active,
                unit="count",
                as_of=now,
                provenance=provenance_trial,
                definition="Current non-INTERNAL_TEST trials in ACTIVE state whose server-side ends_at is in the future.",
            ),
            "trial_expiring": _metric(
                metric_id="trial_expiring",
                status="available",
                value=trial_expiring,
                unit="count",
                as_of=now,
                provenance=provenance_trial,
                definition="Current active non-INTERNAL_TEST trials ending within 7 days.",
            ),
            "trial_expired": _metric(
                metric_id="trial_expired",
                status="available",
                value=trial_expired,
                unit="count",
                as_of=now,
                provenance=provenance_trial,
                quality="reconciled",
                definition="Non-INTERNAL_TEST trials currently EXPIRED whose last state update occurred in the rolling 30-day window.",
            ),
            "trial_converted": _metric(
                metric_id="trial_converted",
                status="available",
                value=trial_converted,
                unit="count",
                as_of=now,
                provenance=provenance_trial,
                definition="Non-INTERNAL_TEST trials with converted_at inside the rolling 30-day window.",
            ),
            "conversion_rate": _metric(
                metric_id="conversion_rate",
                status="available" if conversion_rate is not None else "unavailable",
                value=(
                    str(conversion_rate.quantize(Decimal("0.01")))
                    if conversion_rate is not None
                    else None
                ),
                unit="percent",
                as_of=now,
                provenance=provenance_trial,
                quality="verified" if conversion_rate is not None else "missing",
                definition="Percent of trials started in the rolling 30-day cohort that converted by as_of; unavailable when the cohort is empty.",
            ),
            "subscription_active": _metric(
                metric_id="subscription_active",
                status="available",
                value=subscription_active,
                unit="count",
                as_of=now,
                provenance=provenance_subscription,
                definition="Current non-INTERNAL_TEST subscriptions in ACTIVE state.",
            ),
            "past_due": _metric(
                metric_id="past_due",
                status="available",
                value=past_due,
                unit="count",
                as_of=now,
                provenance=provenance_subscription,
                definition="Current non-INTERNAL_TEST subscriptions in PAST_DUE state.",
            ),
            "churn": _metric(
                metric_id="churn",
                status=churn["status"],
                value=churn["value"],
                unit="percent",
                as_of=now,
                provenance=(
                    "table:fm_commercial_outbox_v1",
                    "table:fm_customers_v1",
                ),
                quality=churn["quality_status"],
                definition="30-day gross logo churn: subscriptions active immediately before the window that emitted subscription.canceled during the window divided by that starting active base.",
            ),
            "mrr": _metric(
                metric_id="mrr",
                status=money_status,
                value={
                    "by_currency": _money_by_currency(mrr),
                    "unsupported_active_periods": dict(sorted(unsupported_periods.items())),
                },
                unit="currency_per_month",
                as_of=now,
                provenance=provenance_subscription,
                quality=money_quality,
                definition="MRR from current active subscriptions: monthly amount as-is, annual amount / 12; currencies remain separate and unsupported periods are excluded explicitly.",
            ),
            "arr": _metric(
                metric_id="arr",
                status=money_status,
                value={
                    "by_currency": _money_by_currency(arr),
                    "unsupported_active_periods": dict(sorted(unsupported_periods.items())),
                },
                unit="currency_per_year",
                as_of=now,
                provenance=provenance_subscription,
                quality=money_quality,
                definition="ARR from current active subscriptions: monthly amount * 12, annual amount as-is; currencies remain separate and unsupported periods are excluded explicitly.",
            ),
            "payment_success": _metric(
                metric_id="payment_success",
                status="available",
                value=payment_success,
                unit="count",
                as_of=now,
                provenance=provenance_billing,
                definition="Succeeded payment transactions whose provider occurrence/update timestamp is inside the rolling 30-day window.",
            ),
            "payment_failure": _metric(
                metric_id="payment_failure",
                status="available",
                value=payment_failure,
                unit="count",
                as_of=now,
                provenance=provenance_billing,
                definition="Failed payment transactions whose provider occurrence/update timestamp is inside the rolling 30-day window.",
            ),
        }

    @staticmethod
    def _churn(*, now: datetime, window_start: datetime, subscription_events) -> dict[str, Any]:
        latest_before: dict[str, tuple[datetime, str]] = {}
        canceled_in_window: set[str] = set()
        for row in subscription_events:
            occurred = _utc(row.occurred_at)
            payload = dict(row.payload or {})
            status = str(payload.get("status") or "").strip().casefold()
            if occurred < window_start and status:
                previous = latest_before.get(row.aggregate_id)
                if previous is None or occurred > previous[0]:
                    latest_before[row.aggregate_id] = (occurred, status)
            if (
                window_start <= occurred <= now
                and row.event_type == "subscription.canceled"
            ):
                canceled_in_window.add(row.aggregate_id)

        starting_active = {
            subscription_id
            for subscription_id, (_, status) in latest_before.items()
            if status == "active"
        }
        if not starting_active:
            return {
                "status": "unavailable",
                "value": None,
                "quality_status": "missing",
            }
        lost = len(starting_active.intersection(canceled_in_window))
        rate = Decimal(lost) * Decimal(100) / Decimal(len(starting_active))
        return {
            "status": "available",
            "value": str(rate.quantize(Decimal("0.01"))),
            "quality_status": "reconciled",
        }

    @staticmethod
    def _finops(*, now: datetime, rows, entitlements) -> dict[str, Any]:
        plan_by_tenant = {
            row.tenant_id: row.plan_code or "UNASSIGNED"
            for row in entitlements
        }
        per_tenant: dict[str, dict[str, Any]] = {}
        usage_by_plan: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "attempts": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
            }
        )
        unknown_events = 0

        for row in rows:
            tenant = per_tenant.setdefault(
                row.tenant_id,
                {
                    "tenant_id": row.tenant_id,
                    "costs": defaultdict(Decimal),
                    "cost_known_events": 0,
                    "cost_unknown_events": 0,
                    "attempts": 0,
                },
            )
            tenant["attempts"] += row.attempts
            tenant["cost_known_events"] += row.cost_known_events
            tenant["cost_unknown_events"] += row.cost_unknown_events
            unknown_events += row.cost_unknown_events
            if row.moeda != "XXX":
                tenant["costs"][row.moeda] += Decimal(row.cost_total)

            plan = plan_by_tenant.get(row.tenant_id, "UNASSIGNED")
            usage = usage_by_plan[plan]
            usage["attempts"] += row.attempts
            usage["input_tokens"] += row.input_tokens
            usage["output_tokens"] += row.output_tokens
            usage["cached_tokens"] += row.cached_tokens

        serialized_tenants = []
        for tenant_id in sorted(per_tenant):
            item = per_tenant[tenant_id]
            known = int(item["cost_known_events"])
            unknown = int(item["cost_unknown_events"])
            serialized_tenants.append(
                {
                    "tenant_id": tenant_id,
                    "attempts": int(item["attempts"]),
                    "cost_known_events": known,
                    "cost_unknown_events": unknown,
                    "quality_status": "partial" if unknown else "verified",
                    "costs": _money_by_currency(dict(item["costs"])),
                    "provenance_refs": [
                        "table:fm_ai_finops_daily_v1",
                        f"tenant:{tenant_id}",
                    ],
                }
            )

        return {
            "ai_cost_per_tenant": {
                "status": "available",
                "as_of": _iso(now),
                "source_authority": "kordena_ai_finops",
                "quality_status": "partial" if unknown_events else "verified",
                "tenants": serialized_tenants,
                "provenance_refs": ["table:fm_ai_finops_daily_v1"],
            },
            "infra_cost_per_tenant": {
                "status": "unavailable",
                "as_of": _iso(now),
                "source_authority": "not_configured",
                "quality_status": "missing",
                "tenants": None,
                "provenance_refs": [],
                "reason": "infrastructure_cost_source_not_configured",
            },
            "usage_by_plan": {
                "status": "available",
                "as_of": _iso(now),
                "source_authority": "kordena_ai_finops+commercial_entitlement",
                "quality_status": "verified",
                "plans": [
                    {"plan_code": plan_code, **values}
                    for plan_code, values in sorted(usage_by_plan.items())
                ],
                "provenance_refs": [
                    "table:fm_ai_finops_daily_v1",
                    "table:fm_kordena_entitlement_projection_v1",
                ],
            },
            "cost_unknown_events": unknown_events,
        }

    @staticmethod
    def _antiabuse(*, now: datetime, signups, provisioning, trials, audits) -> dict[str, Any]:
        one_hour_ago = now - timedelta(hours=1)
        signup_rate_last_hour = sum(
            _utc(row.created_at) >= one_hour_ago for row in signups
        )
        signup_resends = sum(row.resend_count for row in signups)

        trial_counts = Counter(row.fm_customer_id for row in trials)
        repeated_trial_customers = sum(
            count > 1 for count in trial_counts.values()
        )
        trial_overrides = sum(
            row.action == "commercial.trial.activate"
            and bool(dict(row.metadata_safe or {}).get("override_antiabuse"))
            for row in audits
        )
        provisioning_failures = sum(
            row.status == "failed_retryable" for row in provisioning
        )

        return {
            "signup_rate_last_hour": signup_rate_last_hour,
            "signup_resends_30d": signup_resends,
            "repeated_trial_customers": repeated_trial_customers,
            "trial_admin_overrides_30d": trial_overrides,
            "provisioning_failed_retryable_30d": provisioning_failures,
            "risk_score": None,
            "policy_thresholds": "not_configured",
            "source_authority": "fm_commercial_platform",
            "provenance_refs": [
                "table:fm_public_signup_intents_v1",
                "table:fm_commercial_trials_v1",
                "table:fm_commercial_audit_v1",
                "table:fm_commercial_provisioning_sagas_v1",
            ],
        }

    @staticmethod
    def _health(*, now: datetime, provisioning, entitlements, webhooks, finops) -> dict[str, Any]:
        stale_entitlements = sum(_utc(row.valid_until) <= now for row in entitlements)
        dead_letters = sum(row.status == "dead_letter" for row in webhooks)
        retryable_webhooks = sum(
            row.status == "failed_retryable" for row in webhooks
        )
        failed_provisioning = sum(
            row.status == "failed_retryable" for row in provisioning
        )
        return {
            "stale_entitlements": stale_entitlements,
            "webhook_dead_letters_30d": dead_letters,
            "webhook_failed_retryable_30d": retryable_webhooks,
            "provisioning_failed_retryable_30d": failed_provisioning,
            "ai_cost_unknown_events_30d": finops["cost_unknown_events"],
            "status": (
                "degraded"
                if stale_entitlements
                or dead_letters
                or retryable_webhooks
                or failed_provisioning
                or finops["cost_unknown_events"]
                else "healthy"
            ),
            "source_authority": "fm_commercial_platform",
            "provenance_refs": [
                "table:fm_kordena_entitlement_projection_v1",
                "table:fm_billing_webhook_inbox_v1",
                "table:fm_commercial_provisioning_sagas_v1",
                "table:fm_ai_finops_daily_v1",
            ],
        }

    @staticmethod
    def _alerts(*, antiabuse: dict[str, Any], health: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = (
            (
                "kca13.entitlement.stale",
                "high",
                int(health["stale_entitlements"]),
                "Commercial entitlement projections are stale.",
            ),
            (
                "kca13.webhook.dead_letter",
                "high",
                int(health["webhook_dead_letters_30d"]),
                "Billing webhook events reached DEAD_LETTER.",
            ),
            (
                "kca13.webhook.retryable_failure",
                "medium",
                int(health["webhook_failed_retryable_30d"]),
                "Billing webhook events remain retryable failures.",
            ),
            (
                "kca13.provisioning.retryable_failure",
                "medium",
                int(health["provisioning_failed_retryable_30d"]),
                "Provisioning sagas remain in retryable failure.",
            ),
            (
                "kca13.trial.repeated_customer",
                "high",
                int(antiabuse["repeated_trial_customers"]),
                "More than one trial record exists for the same commercial customer.",
            ),
            (
                "kca13.ai_cost.unknown",
                "medium",
                int(health["ai_cost_unknown_events_30d"]),
                "AI usage events lack a known monetary cost.",
            ),
        )
        return [
            {
                "code": code,
                "severity": severity,
                "count": count,
                "message": message,
            }
            for code, severity, count, message in candidates
            if count > 0
        ]

    @staticmethod
    def _correlations(*, audits, provisioning, webhooks) -> list[str]:
        values: list[str] = []
        for row in (*audits, *provisioning, *webhooks):
            correlation_id = str(getattr(row, "correlation_id", "") or "").strip()
            if correlation_id and correlation_id not in values:
                values.append(correlation_id)
            if len(values) >= 20:
                break
        return values
