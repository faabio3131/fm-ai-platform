from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra.ai_finops_models import AIFinOpsBase
from infra.ai_finops_projector import AIFinOpsProjector
from infra.ai_metering import AIMeteringBase, AIUsageEventORM


def _event(index: int) -> AIUsageEventORM:
    return AIUsageEventORM(
        usage_event_id=f"event-{index}",
        tenant_id="tenant-a",
        unidade_id="unit-a",
        request_id=f"request-{index}",
        correlation_id=f"corr-{index}",
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
        custo_real_calculado=None,
        moeda=None,
        price_snapshot_id="snapshot-a",
        timestamp=datetime(2026, 8, 28, tzinfo=timezone.utc)
        + timedelta(seconds=index),
    )


def test_af30_projector_respeita_budget_explicito_de_lote() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    AIMeteringBase.metadata.create_all(engine)
    AIFinOpsBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory.begin() as session:
        session.add_all(_event(index) for index in range(5))

    projector = AIFinOpsProjector(factory)
    assert projector.project_batch(limite=2).processed_events == 2
    assert projector.project_batch(limite=2).processed_events == 2
    assert projector.project_batch(limite=2).processed_events == 1
    assert projector.project_batch(limite=2).processed_events == 0

    with pytest.raises(ValueError, match="limite_lote_invalido"):
        projector.project_batch(limite=0)
