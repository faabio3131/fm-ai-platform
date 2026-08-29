"""Leitura tenant-safe do agregado AI FinOps, sem consultar usage bruto."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.ai_finops import AIFinOpsBucket, PortaAIFinOpsReadModel
from infra.ai_finops_models import AIFinOpsDailyORM


class AIFinOpsSQLAlchemyReadModel(PortaAIFinOpsReadModel):
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def listar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        inicio: date,
        fim: date,
    ) -> tuple[AIFinOpsBucket, ...]:
        tenant = tenant_id.strip()
        unidade = unidade_id.strip()
        if not tenant:
            raise ValueError("ai_finops.tenant_id_obrigatorio")
        if not unidade:
            raise ValueError("ai_finops.unidade_id_obrigatorio")
        if fim < inicio:
            raise ValueError("ai_finops.periodo_invalido")

        with self._session_factory() as session:
            rows = tuple(
                session.scalars(
                    select(AIFinOpsDailyORM)
                    .where(
                        AIFinOpsDailyORM.tenant_id == tenant,
                        AIFinOpsDailyORM.unidade_id == unidade,
                        AIFinOpsDailyORM.bucket_date >= inicio,
                        AIFinOpsDailyORM.bucket_date <= fim,
                    )
                    .order_by(
                        AIFinOpsDailyORM.bucket_date,
                        AIFinOpsDailyORM.provider,
                        AIFinOpsDailyORM.model,
                        AIFinOpsDailyORM.capability,
                        AIFinOpsDailyORM.outcome,
                        AIFinOpsDailyORM.moeda,
                    )
                ).all()
            )

        return tuple(
            AIFinOpsBucket(
                tenant_id=row.tenant_id,
                unidade_id=row.unidade_id,
                bucket_date=row.bucket_date,
                provider=row.provider,
                model=row.model,
                capability=row.capability,
                outcome=row.outcome,
                moeda=row.moeda,
                attempts=row.attempts,
                fallback_attempts=row.fallback_attempts,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
                cached_tokens=row.cached_tokens,
                latency_ms_total=row.latency_ms_total,
                latency_ms_max=row.latency_ms_max,
                cost_known_events=row.cost_known_events,
                cost_unknown_events=row.cost_unknown_events,
                cost_total=Decimal(row.cost_total),
            )
            for row in rows
        )
