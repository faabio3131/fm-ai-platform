"""Projeção incremental e idempotente de usage bruto para agregados AI FinOps."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from infra.ai_finops_models import AIFinOpsDailyORM, AIFinOpsProjectedEventORM
from infra.ai_metering import AIUsageEventORM

UNKNOWN_CURRENCY = "XXX"


@dataclass(frozen=True, kw_only=True)
class ProjectionBatchResult:
    processed_events: int
    touched_aggregates: int


@dataclass(kw_only=True)
class _Delta:
    aggregate_id: str
    tenant_id: str
    unidade_id: str
    bucket_date: date
    provider: str
    model: str
    capability: str
    outcome: str
    moeda: str
    attempts: int = 0
    fallback_attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    latency_ms_total: int = 0
    latency_ms_max: int = 0
    cost_known_events: int = 0
    cost_unknown_events: int = 0
    cost_total: Decimal = Decimal(0)


def _aggregate_id(evento: AIUsageEventORM, moeda: str) -> str:
    material = (
        f"{evento.tenant_id}|{evento.unidade_id}|{evento.timestamp.date().isoformat()}|"
        f"{evento.provider}|{evento.model}|{evento.capability}|{evento.outcome}|{moeda}"
    )
    return str(uuid5(NAMESPACE_URL, material))


def _non_negative(valor: int | None, campo: str) -> int:
    if valor is None:
        return 0
    if valor < 0:
        raise ValueError(f"ai_finops.{campo}_negativo")
    return valor


def _cost(evento: AIUsageEventORM) -> tuple[str, int, int, Decimal]:
    valor = evento.custo_real_calculado
    if valor is None:
        return UNKNOWN_CURRENCY, 0, 1, Decimal(0)

    decimal = Decimal(valor)
    if not decimal.is_finite() or decimal < 0:
        raise ValueError("ai_finops.custo_invalido")

    if evento.moeda is None:
        raise ValueError("ai_finops.custo_sem_moeda")

    moeda = evento.moeda.strip().upper()
    if len(moeda) != 3 or not moeda.isascii() or not moeda.isalpha():
        raise ValueError("ai_finops.moeda_invalida")

    return moeda, 1, 0, decimal


def _delta(evento: AIUsageEventORM) -> _Delta:
    moeda, known, unknown, custo = _cost(evento)
    latency = _non_negative(evento.latency_ms, "latency_ms")
    return _Delta(
        aggregate_id=_aggregate_id(evento, moeda),
        tenant_id=evento.tenant_id,
        unidade_id=evento.unidade_id,
        bucket_date=evento.timestamp.date(),
        provider=evento.provider,
        model=evento.model,
        capability=evento.capability,
        outcome=evento.outcome,
        moeda=moeda,
        attempts=1,
        fallback_attempts=1 if evento.fallback_used else 0,
        input_tokens=_non_negative(evento.input_tokens, "input_tokens"),
        output_tokens=_non_negative(evento.output_tokens, "output_tokens"),
        cached_tokens=_non_negative(evento.cached_tokens, "cached_tokens"),
        latency_ms_total=latency,
        latency_ms_max=latency,
        cost_known_events=known,
        cost_unknown_events=unknown,
        cost_total=custo,
    )


def _merge(target: _Delta, source: _Delta) -> None:
    target.attempts += source.attempts
    target.fallback_attempts += source.fallback_attempts
    target.input_tokens += source.input_tokens
    target.output_tokens += source.output_tokens
    target.cached_tokens += source.cached_tokens
    target.latency_ms_total += source.latency_ms_total
    target.latency_ms_max = max(target.latency_ms_max, source.latency_ms_max)
    target.cost_known_events += source.cost_known_events
    target.cost_unknown_events += source.cost_unknown_events
    target.cost_total += source.cost_total


class AIFinOpsProjector:
    """Processa apenas eventos ainda não projetados, em lote explicitamente limitado."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._session_factory = session_factory
        self._now = now

    def project_batch(self, *, limite: int = 500) -> ProjectionBatchResult:
        if not 1 <= limite <= 5_000:
            raise ValueError("ai_finops.limite_lote_invalido")

        with self._session_factory() as session, session.begin():
            projected = exists().where(
                AIFinOpsProjectedEventORM.usage_event_id
                == AIUsageEventORM.usage_event_id
            )
            eventos = tuple(
                session.scalars(
                    select(AIUsageEventORM)
                    .where(~projected)
                    .order_by(AIUsageEventORM.timestamp, AIUsageEventORM.usage_event_id)
                    .limit(limite)
                ).all()
            )

            if not eventos:
                return ProjectionBatchResult(processed_events=0, touched_aggregates=0)

            deltas: dict[str, _Delta] = {}
            for evento in eventos:
                current = _delta(evento)
                existing = deltas.get(current.aggregate_id)
                if existing is None:
                    deltas[current.aggregate_id] = current
                else:
                    _merge(existing, current)

            aggregate_ids = tuple(deltas)
            persisted = {
                row.aggregate_id: row
                for row in session.scalars(
                    select(AIFinOpsDailyORM).where(
                        AIFinOpsDailyORM.aggregate_id.in_(aggregate_ids)
                    )
                ).all()
            }

            for aggregate_id, delta in deltas.items():
                row = persisted.get(aggregate_id)
                if row is None:
                    session.add(
                        AIFinOpsDailyORM(
                            aggregate_id=delta.aggregate_id,
                            tenant_id=delta.tenant_id,
                            unidade_id=delta.unidade_id,
                            bucket_date=delta.bucket_date,
                            provider=delta.provider,
                            model=delta.model,
                            capability=delta.capability,
                            outcome=delta.outcome,
                            moeda=delta.moeda,
                            attempts=delta.attempts,
                            fallback_attempts=delta.fallback_attempts,
                            input_tokens=delta.input_tokens,
                            output_tokens=delta.output_tokens,
                            cached_tokens=delta.cached_tokens,
                            latency_ms_total=delta.latency_ms_total,
                            latency_ms_max=delta.latency_ms_max,
                            cost_known_events=delta.cost_known_events,
                            cost_unknown_events=delta.cost_unknown_events,
                            cost_total=delta.cost_total,
                        )
                    )
                    continue

                row.attempts += delta.attempts
                row.fallback_attempts += delta.fallback_attempts
                row.input_tokens += delta.input_tokens
                row.output_tokens += delta.output_tokens
                row.cached_tokens += delta.cached_tokens
                row.latency_ms_total += delta.latency_ms_total
                row.latency_ms_max = max(row.latency_ms_max, delta.latency_ms_max)
                row.cost_known_events += delta.cost_known_events
                row.cost_unknown_events += delta.cost_unknown_events
                row.cost_total += delta.cost_total

            projected_at = self._now()
            if projected_at.tzinfo is None or projected_at.utcoffset() is None:
                raise ValueError("ai_finops.projected_at_sem_timezone")

            for evento in eventos:
                session.add(
                    AIFinOpsProjectedEventORM(
                        usage_event_id=evento.usage_event_id,
                        projected_at=projected_at.astimezone(timezone.utc),
                    )
                )

            return ProjectionBatchResult(
                processed_events=len(eventos),
                touched_aggregates=len(deltas),
            )
