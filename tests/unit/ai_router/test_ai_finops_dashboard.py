from __future__ import annotations

from datetime import date
from decimal import Decimal

from application.ai_finops_dashboard import resumir_ai_finops
from core.ai_finops import AIFinOpsBucket


def _bucket(
    *,
    outcome: str,
    moeda: str,
    attempts: int,
    fallback_attempts: int,
    cost_known_events: int,
    cost_unknown_events: int,
    cost_total: Decimal,
    provider: str = "provider-a",
    model: str = "model-a",
    latency_ms_total: int = 100,
    latency_ms_max: int = 100,
) -> AIFinOpsBucket:
    return AIFinOpsBucket(
        tenant_id="tenant-a",
        unidade_id="unit-a",
        bucket_date=date(2026, 8, 28),
        provider=provider,
        model=model,
        capability="tool_planning",
        outcome=outcome,
        moeda=moeda,
        attempts=attempts,
        fallback_attempts=fallback_attempts,
        input_tokens=attempts * 10,
        output_tokens=attempts * 5,
        cached_tokens=attempts * 2,
        latency_ms_total=latency_ms_total,
        latency_ms_max=latency_ms_max,
        cost_known_events=cost_known_events,
        cost_unknown_events=cost_unknown_events,
        cost_total=cost_total,
    )


def test_dashboard_resume_metricas_sem_misturar_moedas() -> None:
    resumo = resumir_ai_finops(
        (
            _bucket(
                outcome="success",
                moeda="USD",
                attempts=2,
                fallback_attempts=1,
                cost_known_events=2,
                cost_unknown_events=0,
                cost_total=Decimal("1.20"),
                latency_ms_total=300,
                latency_ms_max=200,
            ),
            _bucket(
                outcome="definitive_failure",
                moeda="USD",
                attempts=1,
                fallback_attempts=0,
                cost_known_events=1,
                cost_unknown_events=0,
                cost_total=Decimal("0.30"),
            ),
            _bucket(
                outcome="success",
                moeda="BRL",
                attempts=1,
                fallback_attempts=0,
                cost_known_events=1,
                cost_unknown_events=0,
                cost_total=Decimal("2.50"),
                provider="provider-b",
                model="model-b",
            ),
            _bucket(
                outcome="success",
                moeda="XXX",
                attempts=1,
                fallback_attempts=0,
                cost_known_events=0,
                cost_unknown_events=1,
                cost_total=Decimal(0),
                provider="provider-b",
                model="model-b",
            ),
        )
    )

    assert resumo.attempts == 5
    assert resumo.success_attempts == 4
    assert resumo.failure_attempts == 1
    assert resumo.fallback_attempts == 1
    assert resumo.success_rate_pct == Decimal(80)
    assert resumo.fallback_rate_pct == Decimal(20)
    assert resumo.cost_coverage_pct == Decimal(80)
    assert resumo.cost_unknown_events == 1
    assert resumo.latency_ms_average == Decimal(120)
    assert resumo.latency_ms_max == 200
    assert [(item.moeda, item.valor) for item in resumo.custos] == [
        ("BRL", Decimal("2.50")),
        ("USD", Decimal("1.50")),
    ]
    assert [(item.provider, item.model, item.attempts) for item in resumo.mix] == [
        ("provider-a", "model-a", 3),
        ("provider-b", "model-b", 2),
    ]


def test_dashboard_vazio_permanece_deterministico() -> None:
    resumo = resumir_ai_finops(())

    assert resumo.attempts == 0
    assert resumo.success_rate_pct == Decimal(0)
    assert resumo.fallback_rate_pct == Decimal(0)
    assert resumo.cost_coverage_pct == Decimal(0)
    assert resumo.custos == ()
    assert resumo.mix == ()
