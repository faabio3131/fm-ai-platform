"""Migration 0048 — bridge fiscal para a autoridade financeira canônica."""

from typing import cast

from sqlalchemy import Table
from sqlalchemy.engine import Connection

from core.pagamentos.modelos_orm import (
    AjusteObrigacaoCompraORM,
    DecisaoCreditoTributarioORM,
    ObrigacaoCompraFiscalORM,
)


def upgrade_fiscal_financial_tax_bridge_v1(connection: Connection) -> None:
    for model in (
        ObrigacaoCompraFiscalORM,
        AjusteObrigacaoCompraORM,
        DecisaoCreditoTributarioORM,
    ):
        cast(Table, model.__table__).create(bind=connection, checkfirst=True)
