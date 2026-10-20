"""Create durable persistence for the Kordena Fiscal V1 integration."""

from sqlalchemy.engine import Connection

from infra.fiscal.modelos_orm import FiscalBase


def upgrade_fiscal_persistence_foundation_v1(connection: Connection) -> None:
    FiscalBase.metadata.create_all(bind=connection, checkfirst=True)
