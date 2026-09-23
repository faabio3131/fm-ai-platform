"""Repositório SQLAlchemy do Commercial Registry KCA-01."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.comercial.erros import ConflitoConcorrenciaComercial
from core.comercial.modelos import (
    ClasseContaComercial,
    ClienteComercial,
    ContaProdutoComercial,
    StatusClienteComercial,
    StatusContaProduto,
)

from .modelos_orm import (
    CommercialAuditORM,
    CommercialIdempotencyORM,
    CommercialOutboxORM,
    FMCustomerORM,
    FMProductAccountORM,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cliente(row: FMCustomerORM) -> ClienteComercial:
    return ClienteComercial(
        fm_customer_id=row.fm_customer_id,
        customer_code=row.customer_code,
        display_name=row.display_name,
        legal_name=row.legal_name,
        status=StatusClienteComercial(row.status),
        account_class=ClasseContaComercial(row.account_class),
        primary_contact_email=row.primary_contact_email,
        primary_contact_phone=row.primary_contact_phone,
        version=row.version,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


def _conta(row: FMProductAccountORM) -> ContaProdutoComercial:
    return ContaProdutoComercial(
        product_account_id=row.product_account_id,
        fm_customer_id=row.fm_customer_id,
        product_code=row.product_code,
        product_tenant_id=row.product_tenant_id,
        status=StatusContaProduto(row.status),
        version=row.version,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        activated_at=_utc(row.activated_at) if row.activated_at else None,
        suspended_at=_utc(row.suspended_at) if row.suspended_at else None,
        closed_at=_utc(row.closed_at) if row.closed_at else None,
    )


class RepositorioComercialSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter_cliente(self, fm_customer_id: str) -> ClienteComercial | None:
        row = self._session.get(FMCustomerORM, fm_customer_id)
        return _cliente(row) if row is not None else None

    def adicionar_cliente(self, row: FMCustomerORM) -> ClienteComercial:
        self._session.add(row)
        self._session.flush()
        return _cliente(row)

    def atualizar_cliente(
        self,
        *,
        fm_customer_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> ClienteComercial:
        statement = (
            update(FMCustomerORM)
            .where(
                FMCustomerORM.fm_customer_id == fm_customer_id,
                FMCustomerORM.version == expected_version,
            )
            .values(**values, version=expected_version + 1)
        )
        if self._session.execute(statement).rowcount != 1:
            raise ConflitoConcorrenciaComercial("customer_version_conflict")
        self._session.flush()
        row = self._session.get(FMCustomerORM, fm_customer_id)
        if row is None:
            raise ConflitoConcorrenciaComercial("customer_missing_after_update")
        return _cliente(row)

    def obter_conta_produto(
        self, product_account_id: str
    ) -> ContaProdutoComercial | None:
        row = self._session.get(FMProductAccountORM, product_account_id)
        return _conta(row) if row is not None else None

    def obter_conta_produto_por_tenant(
        self,
        *,
        product_code: str,
        product_tenant_id: str,
    ) -> ContaProdutoComercial | None:
        row = self._session.scalar(
            select(FMProductAccountORM).where(
                FMProductAccountORM.product_code == product_code.strip().upper(),
                FMProductAccountORM.product_tenant_id == product_tenant_id.strip(),
            )
        )
        return _conta(row) if row is not None else None

    def adicionar_conta_produto(
        self, row: FMProductAccountORM
    ) -> ContaProdutoComercial:
        self._session.add(row)
        self._session.flush()
        return _conta(row)

    def atualizar_conta_produto(
        self,
        *,
        product_account_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> ContaProdutoComercial:
        statement = (
            update(FMProductAccountORM)
            .where(
                FMProductAccountORM.product_account_id == product_account_id,
                FMProductAccountORM.version == expected_version,
            )
            .values(**values, version=expected_version + 1)
        )
        if self._session.execute(statement).rowcount != 1:
            raise ConflitoConcorrenciaComercial("product_account_version_conflict")
        self._session.flush()
        row = self._session.get(FMProductAccountORM, product_account_id)
        if row is None:
            raise ConflitoConcorrenciaComercial(
                "product_account_missing_after_update"
            )
        return _conta(row)

    def obter_idempotencia(
        self, *, scope: str, idempotency_key: str
    ) -> CommercialIdempotencyORM | None:
        return self._session.get(
            CommercialIdempotencyORM,
            {"scope": scope, "idempotency_key": idempotency_key},
        )

    def adicionar_idempotencia(
        self,
        *,
        scope: str,
        idempotency_key: str,
        request_sha256: str,
        aggregate_type: str,
        aggregate_id: str,
        created_at: datetime,
    ) -> None:
        self._session.add(
            CommercialIdempotencyORM(
                scope=scope,
                idempotency_key=idempotency_key,
                request_sha256=request_sha256,
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                created_at=created_at,
            )
        )
        self._session.flush()

    def adicionar_auditoria(self, row: CommercialAuditORM) -> None:
        self._session.add(row)
        self._session.flush()

    def adicionar_outbox(self, row: CommercialOutboxORM) -> None:
        self._session.add(row)
        self._session.flush()

    def listar_outbox(self) -> tuple[CommercialOutboxORM, ...]:
        return tuple(
            self._session.scalars(
                select(CommercialOutboxORM).order_by(
                    CommercialOutboxORM.occurred_at,
                    CommercialOutboxORM.event_id,
                )
            ).all()
        )
