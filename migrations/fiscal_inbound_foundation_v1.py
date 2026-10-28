"""Migration 0045 — complete the additive inbound Fiscal V1 foundation."""

from typing import cast

from sqlalchemy import Index, Table
from sqlalchemy.engine import Connection

from infra.fiscal.modelos_orm import (
    FiscalInboundDocumentORM,
    FiscalInboundItemORM,
    FiscalManifestationORM,
)


def upgrade_fiscal_inbound_foundation_v1(connection: Connection) -> None:
    cast(Table, FiscalInboundItemORM.__table__).create(
        bind=connection,
        checkfirst=True,
    )
    document_table = cast(Table, FiscalInboundDocumentORM.__table__)
    manifestation_table = cast(Table, FiscalManifestationORM.__table__)
    document_index = next(
        index
        for index in document_table.indexes
        if index.name == "ix_fiscal_inbound_partition_status_v1"
    )
    manifestation_index = next(
        index
        for index in manifestation_table.indexes
        if index.name == "ix_fiscal_manifestation_partition_document_v1"
    )
    cast(Index, document_index).create(bind=connection, checkfirst=True)
    cast(Index, manifestation_index).create(bind=connection, checkfirst=True)
