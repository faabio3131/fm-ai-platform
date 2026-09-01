from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from infra.ai_finops_models import AIFinOpsBase, AIFinOpsDailyORM
from infra.ai_finops_read_model import AIFinOpsSQLAlchemyReadModel


def test_af29_leitura_finops_faz_um_select_e_nunca_toca_usage_bruto() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    AIFinOpsBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory.begin() as session:
        session.add(
            AIFinOpsDailyORM(
                aggregate_id="aggregate-a",
                tenant_id="tenant-a",
                unidade_id="unit-a",
                bucket_date=date(2026, 8, 28),
                provider="provider-a",
                model="model-a",
                capability="tool_planning",
                outcome="success",
                moeda="XXX",
                attempts=1,
                fallback_attempts=0,
                input_tokens=1,
                output_tokens=1,
                cached_tokens=0,
                latency_ms_total=1,
                latency_ms_max=1,
                cost_known_events=0,
                cost_unknown_events=1,
                cost_total=0,
            )
        )

    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(str(statement))

    event.listen(engine, "before_cursor_execute", capture)
    try:
        rows = AIFinOpsSQLAlchemyReadModel(factory).listar(
            tenant_id="tenant-a",
            unidade_id="unit-a",
            inicio=date(2026, 8, 28),
            fim=date(2026, 8, 28),
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    selects = [sql for sql in statements if sql.lstrip().upper().startswith("SELECT")]
    assert len(rows) == 1
    assert len(selects) == 1
    assert "fm_ai_finops_daily_v1" in selects[0]
    assert "fm_ai_usage_events_v1" not in selects[0]
