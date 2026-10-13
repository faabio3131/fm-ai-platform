"""Migration 0033 — política canônica de origem e áreas de entrega V1.

Estrutura aditiva, tenant/unidade scoped, sem backfill e sem dados padrão.
Ausência de configuração deve permanecer fail-closed no runtime comercial.
"""

from __future__ import annotations

from sqlalchemy.engine import Connection

from core.delivery.modelos_orm import DeliveryPolicyBase


def upgrade_delivery_policy_v1(connection: Connection) -> None:
    DeliveryPolicyBase.metadata.create_all(
        bind=connection,
        checkfirst=True,
    )
