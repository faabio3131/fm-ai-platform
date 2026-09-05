"""Migration do estado persistente do canal Delivery Próprio V1."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from core.delivery.carrinho_orm import DeliveryChannelBase


def upgrade_delivery_channel_state_v1(connection: Connection) -> None:
    DeliveryChannelBase.metadata.create_all(bind=connection, checkfirst=True)


def revert_delivery_channel_state_v1(connection: Connection) -> None:
    DeliveryChannelBase.metadata.drop_all(bind=connection, checkfirst=True)
