"""Composition root incremental do Delivery Próprio comercial V1."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from infra.delivery.carrinhos_sqlalchemy import RepositorioCarrinhosDeliverySQLAlchemy


@dataclass(frozen=True)
class PersistenciaDeliveryComercialV1:
    carrinhos: RepositorioCarrinhosDeliverySQLAlchemy


def compor_persistencia_delivery(
    session: Session,
) -> PersistenciaDeliveryComercialV1:
    """Compõe somente adapters comerciais persistentes; não abre transação."""

    return PersistenciaDeliveryComercialV1(
        carrinhos=RepositorioCarrinhosDeliverySQLAlchemy(session),
    )
