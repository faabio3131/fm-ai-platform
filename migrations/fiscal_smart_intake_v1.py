"""Migration 0046 — add the authority-aware smart fiscal intake."""

from typing import cast

from sqlalchemy import Table
from sqlalchemy.engine import Connection

from infra.fiscal.modelos_orm import FiscalIntakeCaptureORM


def upgrade_fiscal_smart_intake_v1(connection: Connection) -> None:
    cast(Table, FiscalIntakeCaptureORM.__table__).create(
        bind=connection,
        checkfirst=True,
    )
