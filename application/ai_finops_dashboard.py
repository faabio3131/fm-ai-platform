"""Síntese determinística para o Dashboard AI FinOps."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.ai_finops import AIFinOpsBucket


@dataclass(frozen=True, kw_only=True)
class CustoAIFinOpsPorMoeda:
    moeda: str
    valor: Decimal
    eventos: int


@dataclass(frozen=True, kw_only=True)
class MixAIFinOps:
    provider: str
    model: str
    attempts: int


@dataclass(frozen=True, kw_only=True)
class ResumoAIFinOps:
    attempts: int
    success_attempts: int
    failure_attempts: int
    fallback_attempts: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    latency_ms_average: Decimal
    latency_ms_max: int
    cost_known_events: int
    cost_unknown_events: int
    success_rate_pct: Decimal
    fallback_rate_pct: Decimal
    cost_coverage_pct: Decimal
    custos: tuple[CustoAIFinOpsPorMoeda, ...]
    mix: tuple[MixAIFinOps, ...]


def _percent(parte: int, total: int) -> Decimal:
    if total == 0:
        return Decimal(0)
    return Decimal(parte) * Decimal(100) / Decimal(total)


def resumir_ai_finops(
    buckets: tuple[AIFinOpsBucket, ...],
) -> ResumoAIFinOps:
    attempts = sum(bucket.attempts for bucket in buckets)
    success_attempts = sum(
        bucket.attempts
        for bucket in buckets
        if bucket.outcome == "success"
    )
    failure_attempts = attempts - success_attempts
    fallback_attempts = sum(bucket.fallback_attempts for bucket in buckets)
    input_tokens = sum(bucket.input_tokens for bucket in buckets)
    output_tokens = sum(bucket.output_tokens for bucket in buckets)
    cached_tokens = sum(bucket.cached_tokens for bucket in buckets)
    latency_total = sum(bucket.latency_ms_total for bucket in buckets)
    latency_max = max(
        (bucket.latency_ms_max for bucket in buckets),
        default=0,
    )
    known = sum(bucket.cost_known_events for bucket in buckets)
    unknown = sum(bucket.cost_unknown_events for bucket in buckets)

    custos: dict[str, tuple[Decimal, int]] = {}
    mix: dict[tuple[str, str], int] = {}

    for bucket in buckets:
        chave_mix = (bucket.provider, bucket.model)
        mix[chave_mix] = mix.get(chave_mix, 0) + bucket.attempts

        if bucket.moeda == "XXX":
            if bucket.cost_known_events or bucket.cost_total != Decimal(0):
                raise ValueError("ai_finops.bucket_unknown_currency_invalido")
            continue

        valor, eventos = custos.get(bucket.moeda, (Decimal(0), 0))
        custos[bucket.moeda] = (
            valor + bucket.cost_total,
            eventos + bucket.cost_known_events,
        )

    latency_average = (
        Decimal(latency_total) / Decimal(attempts)
        if attempts
        else Decimal(0)
    )

    return ResumoAIFinOps(
        attempts=attempts,
        success_attempts=success_attempts,
        failure_attempts=failure_attempts,
        fallback_attempts=fallback_attempts,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        latency_ms_average=latency_average,
        latency_ms_max=latency_max,
        cost_known_events=known,
        cost_unknown_events=unknown,
        success_rate_pct=_percent(success_attempts, attempts),
        fallback_rate_pct=_percent(fallback_attempts, attempts),
        cost_coverage_pct=_percent(known, known + unknown),
        custos=tuple(
            CustoAIFinOpsPorMoeda(
                moeda=moeda,
                valor=valor,
                eventos=eventos,
            )
            for moeda, (valor, eventos) in sorted(custos.items())
        ),
        mix=tuple(
            MixAIFinOps(
                provider=provider,
                model=model,
                attempts=quantidade,
            )
            for (provider, model), quantidade in sorted(
                mix.items(),
                key=lambda item: (
                    -item[1],
                    item[0][0],
                    item[0][1],
                ),
            )
        ),
    )
