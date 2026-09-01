from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from infra.ai_finops_models import AIFinOpsBase, AIFinOpsProjectedEventORM
from infra.ai_finops_projector import AIFinOpsProjector
from infra.ai_finops_read_model import AIFinOpsSQLAlchemyReadModel
from infra.ai_metering import AIMeteringBase, AIUsageEventORM


def _event(event_id: str, *, timestamp: datetime) -> AIUsageEventORM:
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
        input_tokens=10,
        output_tokens=5,
        cached_tokens=2,
        latency_ms=25,
        outcome="success",
        custo_real_calculado=None,
        moeda=None,
        price_snapshot_id="snapshot-a",
        timestamp=timestamp,
    )


def test_af23_projection_e_incremental_idempotente_e_aceita_evento_tardio() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    AIMeteringBase.metadata.create_all(engine)
    AIFinOpsBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    base = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)

    with factory.begin() as session:
        session.add_all(
            [
                _event("event-2", timestamp=base + timedelta(seconds=2)),
                _event("event-3", timestamp=base + timedelta(seconds=3)),
            ]
        )

    projector = AIFinOpsProjector(factory, now=lambda: base + timedelta(minutes=1))
    assert projector.project_batch(limite=1).processed_events == 1

    with factory.begin() as session:
        session.add(_event("event-1", timestamp=base + timedelta(seconds=1)))

    assert projector.project_batch(limite=10).processed_events == 2
    assert projector.project_batch(limite=10).processed_events == 0

    with factory() as session:
        projected = session.scalar(
            select(func.count(AIFinOpsProjectedEventORM.usage_event_id))
        )
    assert projected == 3

    buckets = AIFinOpsSQLAlchemyReadModel(factory).listar(
        tenant_id="tenant-a",
        unidade_id="unit-a",
        inicio=base.date(),
        fim=base.date(),
    )
    assert len(buckets) == 1
    bucket = buckets[0]
    assert bucket.attempts == 3
    assert bucket.input_tokens == 30
    assert bucket.output_tokens == 15
    assert bucket.cached_tokens == 6
    assert bucket.cost_known_events == 0
    assert bucket.cost_unknown_events == 3
    assert bucket.cost_total == Decimal(0)
    assert bucket.moeda == "XXX"
