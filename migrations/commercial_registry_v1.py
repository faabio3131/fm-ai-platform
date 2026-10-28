"""Migration 0049 — Commercial Registry + Product Accounts KCA-01."""

from sqlalchemy.engine import Connection

from infra.comercial.modelos_orm import CommercialBase


def upgrade_commercial_registry_v1(connection: Connection) -> None:
    CommercialBase.metadata.create_all(bind=connection, checkfirst=True)
