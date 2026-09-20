"""Migration 0047 — autoridade de Procurement e integração fiscal/estoque."""

from typing import cast

from sqlalchemy import Table
from sqlalchemy.engine import Connection

from infra.procurement.modelos_orm import ProcurementBase


def upgrade_fiscal_procurement_integration_v1(connection: Connection) -> None:
    for table in ProcurementBase.metadata.sorted_tables:
        cast(Table, table).create(bind=connection, checkfirst=True)
