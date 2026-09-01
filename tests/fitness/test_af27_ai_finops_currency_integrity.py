from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra.ai_finops_models import AIFinOpsBase
from infra.ai_finops_projector import AIFinOpsProjector
from infra.ai_finops_read_model import AIFinOpsSQLAlchemyReadModel
from infra.ai_metering import AIMeteringBase, AIUsageEventORM


def _event(
    event_id: str,
    *,
    custo: Decimal | None,
    moeda: str | None,
) -> AIUsageEventORM:
    return AIUsageEventORM(
        usage_event_id=event_id,
        tenant_id="tenant-a",
        unidade_id="unit-a",
        request_id=f"request-{event_id}",
        correlation_id=f"corr-{event_id}",
        capability="tool_planning",
        provider="provider-a",
        model="model-a",
        route_reason="test",
        fallback_used=False,
        fallback_reason=None,
        input_tokens=1,
        output_tokens=1,
        cached_tokens=0,
        latency_ms=1,
        outcome="success",
        custo_real_calculado=custo,
        moeda=moeda,
        price_snapshot_id="snapshot-a",
        timestamp=datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc),
    )


def test_af27_custos_de_moedas_distintas_nunca_sao_misturados() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    AIMeteringBase.metadata.create_all(engine)
    AIFinOpsBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory.begin() as session:
        session.add_all(
            [
                _event("usd", custo=Decimal("1.25"), moeda="USD"),
                _event("brl", custo=Decimal("2.50"), moeda="BRL"),
                _event("unknown", custo=None, moeda=None),
            ]
        )

    assert AIFinOpsProjector(factory).project_batch(limite=10).processed_events == 3
    rows = AIFinOpsSQLAlchemyReadModel(factory).listar(
        tenant_id="tenant-a",
        unidade_id="unit-a",
        inicio=datetime(2026, 8, 28, tzinfo=timezone.utc).date(),
        fim=datetime(2026, 8, 28, tzinfo=timezone.utc).date(),
    )
    by_currency = {row.moeda: row for row in rows}

    assert set(by_currency) == {"BRL", "USD", "XXX"}
    assert by_currency["USD"].cost_total == Decimal("1.25")
    assert by_currency["BRL"].cost_total == Decimal("2.50")
    assert by_currency["XXX"].cost_total == Decimal(0)
    assert by_currency["XXX"].cost_unknown_events == 1
