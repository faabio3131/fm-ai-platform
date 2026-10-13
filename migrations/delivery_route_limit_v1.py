"""Migration 0069 — limite de percurso de entrega por tenant/unidade; sem backfill."""
from sqlalchemy.engine import Connection
from infra.delivery.alcance_sqlalchemy import AlcanceEntregaORM


def upgrade_delivery_route_limit_v1(connection: Connection) -> None:
    AlcanceEntregaORM.__table__.create(bind=connection, checkfirst=True)
