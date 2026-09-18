"""Persistência do vínculo Marketplace -> Pedido canônico para WP-012."""

from sqlalchemy.engine import Connection

from infra.marketplaces.modelos_orm import MarketplaceBase


def upgrade_marketplace_orders_web_v1(connection: Connection) -> None:
    MarketplaceBase.metadata.create_all(bind=connection, checkfirst=True)


def revert_marketplace_orders_web_v1(connection: Connection) -> None:
    MarketplaceBase.metadata.drop_all(bind=connection, checkfirst=True)
