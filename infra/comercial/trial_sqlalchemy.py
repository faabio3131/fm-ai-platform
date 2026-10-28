"""Repositório SQLAlchemy do Trial Engine KCA-07."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.comercial.erros import ConflitoConcorrenciaComercial
from core.comercial.trial import EstadoTrial, PoliticaTrial, TrialComercial

from .trial_orm import FMCommercialTrialORM, FMCommercialTrialPolicyORM


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _policy(row: FMCommercialTrialPolicyORM) -> PoliticaTrial:
    return PoliticaTrial(
        policy_version=row.policy_version,
        duration_days=row.duration_days,
        active=row.active,
        effective_from=_utc(row.effective_from),  # type: ignore[arg-type]
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
    )


def _trial(row: FMCommercialTrialORM) -> TrialComercial:
    return TrialComercial(
        trial_id=row.trial_id,
        fm_customer_id=row.fm_customer_id,
        product_account_id=row.product_account_id,
        tenant_id=row.tenant_id,
        plan_code=row.plan_code,
        plan_version_id=row.plan_version_id,
        status=EstadoTrial(row.status),
        policy_version=row.policy_version,
        duration_days=row.duration_days,
        started_at=_utc(row.started_at),
        ends_at=_utc(row.ends_at),
        converted_at=_utc(row.converted_at),
        revoked_at=_utc(row.revoked_at),
        override_reason=row.override_reason,
        version=row.version,
        correlation_id=row.correlation_id,
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
    )


class RepositorioTrialComercialSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def politica_efetiva(self, *, instante: datetime) -> PoliticaTrial | None:
        row = self._session.scalar(
            select(FMCommercialTrialPolicyORM)
            .where(
                FMCommercialTrialPolicyORM.active.is_(True),
                FMCommercialTrialPolicyORM.effective_from <= instante,
            )
            .order_by(FMCommercialTrialPolicyORM.effective_from.desc())
            .limit(1)
        )
        return _policy(row) if row is not None else None

    def obter(self, trial_id: str) -> TrialComercial | None:
        row = self._session.get(FMCommercialTrialORM, trial_id)
        return _trial(row) if row is not None else None

    def obter_por_product_account(self, product_account_id: str) -> TrialComercial | None:
        row = self._session.scalar(
            select(FMCommercialTrialORM).where(
                FMCommercialTrialORM.product_account_id == product_account_id
            )
        )
        return _trial(row) if row is not None else None

    def listar_por_customer(self, fm_customer_id: str) -> tuple[TrialComercial, ...]:
        rows = self._session.scalars(
            select(FMCommercialTrialORM)
            .where(FMCommercialTrialORM.fm_customer_id == fm_customer_id)
            .order_by(FMCommercialTrialORM.created_at, FMCommercialTrialORM.trial_id)
        ).all()
        return tuple(_trial(row) for row in rows)

    def adicionar(self, row: FMCommercialTrialORM) -> TrialComercial:
        self._session.add(row)
        self._session.flush()
        return _trial(row)

    def atualizar(
        self,
        *,
        trial_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> TrialComercial:
        payload = dict(values)
        payload["version"] = expected_version + 1
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self._session.execute(
            update(FMCommercialTrialORM)
            .where(
                FMCommercialTrialORM.trial_id == trial_id,
                FMCommercialTrialORM.version == expected_version,
            )
            .values(**payload)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ConflitoConcorrenciaComercial("trial_version_conflict")
        self._session.flush()
        current = self.obter(trial_id)
        if current is None:
            raise ConflitoConcorrenciaComercial("trial_missing_after_update")
        return current

    def listar_expiraveis(
        self, *, instante: datetime, limite: int
    ) -> tuple[TrialComercial, ...]:
        rows = self._session.scalars(
            select(FMCommercialTrialORM)
            .where(
                FMCommercialTrialORM.status == EstadoTrial.ACTIVE.value,
                FMCommercialTrialORM.ends_at <= instante,
            )
            .order_by(FMCommercialTrialORM.ends_at, FMCommercialTrialORM.trial_id)
            .limit(limite)
        ).all()
        return tuple(_trial(row) for row in rows)
