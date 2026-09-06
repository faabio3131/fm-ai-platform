"""Resolução comercial scoped da ponte Cliente legado → ClienteCRM."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.crm.modelos import moeda
from infra.crm.cliente_legado_schema import crm_cliente_legado_v1
from infra.legacy_schema import clientes


@dataclass(frozen=True)
class VinculoClienteLegadoCRM:
    legacy_cliente_id: int
    cliente_id: str
    saldo_cashback_legado: Decimal


class LeitorClienteLegadoCRMSQLAlchemy:
    """Resolve somente mapping explícito no Active Scope; nunca cria fallback."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def resolver(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        legacy_cliente_id: int,
    ) -> VinculoClienteLegadoCRM | None:
        row = self._session.execute(
            select(
                crm_cliente_legado_v1.c.legacy_cliente_id,
                crm_cliente_legado_v1.c.cliente_id,
                clientes.c.saldo_cashback,
            )
            .join(
                clientes,
                clientes.c.id == crm_cliente_legado_v1.c.legacy_cliente_id,
            )
            .where(
                crm_cliente_legado_v1.c.tenant_id == tenant_id,
                crm_cliente_legado_v1.c.unidade_id == unidade_id,
                crm_cliente_legado_v1.c.legacy_cliente_id == legacy_cliente_id,
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        return VinculoClienteLegadoCRM(
            legacy_cliente_id=int(row["legacy_cliente_id"]),
            cliente_id=str(row["cliente_id"]),
            saldo_cashback_legado=moeda(Decimal(str(row["saldo_cashback"] or 0))),
        )
