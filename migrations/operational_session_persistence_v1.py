"""Migration 0059 — persistência de sessões operacionais entre processos."""

from __future__ import annotations

from typing import cast

from sqlalchemy import Table
from sqlalchemy.engine import Connection

from infra.seguranca.modelos_orm import OperationalSessionORM


def upgrade_operational_session_persistence_v1(connection: Connection) -> None:
    cast(Table, OperationalSessionORM.__table__).create(
        bind=connection, checkfirst=True
    )
