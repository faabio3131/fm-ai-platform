from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Integer, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from core.ai_router import AIUsageEvent, CapabilityIA, OutcomeIA
from infra.ai_metering import AIMeteringBase, AIUsageDurableMetering, AIUsageEventORM


class BusinessBase(DeclarativeBase):
    pass


class BusinessRow(BusinessBase):
    __tablename__ = "business_rollback_probe"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    value: Mapped[str] = mapped_column(String(32), nullable=False)


def _evento(*, outcome: OutcomeIA, request_id: str) -> AIUsageEvent:
    return AIUsageEvent(
        tenant_id="tenant-metering",
        unidade_id="unidade-metering",
        request_id=request_id,
        correlation_id=f"corr-{request_id}",
        capability=CapabilityIA.TOOL_PLANNING,
        provider="provider-test",
        model="model-test",
        route_reason="capability=tool_planning;priority=100",
        fallback_used=False,
        fallback_reason=None,
        input_tokens=10 if outcome is OutcomeIA.SUCESSO else None,
        output_tokens=5 if outcome is OutcomeIA.SUCESSO else None,
        cached_tokens=0 if outcome is OutcomeIA.SUCESSO else None,
        latency_ms=12,
        outcome=outcome,
        custo_real_calculado=(
            Decimal("0.00125") if outcome is OutcomeIA.SUCESSO else None
        ),
        moeda="USD" if outcome is OutcomeIA.SUCESSO else None,
        price_snapshot_id="snapshot-metering-v1",
        timestamp=datetime(2026, 8, 28, 23, 30, tzinfo=timezone.utc),
    )


def test_ai_usage_sucesso_e_falha_sobrevivem_rollback_da_uow_de_negocio(
    tmp_path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'metering.db'}")
    AIMeteringBase.metadata.create_all(engine)
    BusinessBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    metering = AIUsageDurableMetering(factory)

    with factory() as business_session:
        transaction = business_session.begin()
        assert business_session.in_transaction()

        business_session.add(BusinessRow(id=1, value="rollback"))

        metering.registrar(
            _evento(
                outcome=OutcomeIA.SUCESSO,
                request_id="req-success",
            )
        )
        metering.registrar(
            _evento(
                outcome=OutcomeIA.FALHA_DEFINITIVA,
                request_id="req-failure",
            )
        )

        business_session.flush()
        transaction.rollback()

    with factory() as verification:
        assert verification.scalar(
            select(func.count()).select_from(BusinessRow)
        ) == 0

        eventos = verification.scalars(
            select(AIUsageEventORM).order_by(AIUsageEventORM.request_id)
        ).all()

        assert len(eventos) == 2
        assert {evento.outcome for evento in eventos} == {
            OutcomeIA.SUCESSO.value,
            OutcomeIA.FALHA_DEFINITIVA.value,
        }


def test_ai_usage_metering_e_idempotente_para_o_mesmo_evento(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'metering-idem.db'}")
    AIMeteringBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    metering = AIUsageDurableMetering(factory)
    evento = _evento(outcome=OutcomeIA.SUCESSO, request_id="req-idem")

    metering.registrar(evento)
    metering.registrar(evento)

    with factory() as verification:
        assert verification.scalar(
            select(func.count()).select_from(AIUsageEventORM)
        ) == 1
