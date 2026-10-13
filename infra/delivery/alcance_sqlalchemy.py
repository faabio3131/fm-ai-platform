"""Persistência isolada por tenant/unidade da política máxima de percurso."""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from core.delivery.alcance_rota import AlcanceEntrega
from core.delivery.modelos_orm import DeliveryPolicyBase


class AlcanceEntregaORM(DeliveryPolicyBase):
    __tablename__ = "delivery_alcance_unidade_v1"
    __table_args__ = (CheckConstraint("limite_km BETWEEN 1 AND 200", name="ck_alcance_entrega_km"),)

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    limite_km: Mapped[int] = mapped_column(Integer, nullable=False)


def obter_alcance(session: Session, *, tenant_id: str, unidade_id: str) -> AlcanceEntrega | None:
    row = session.get(AlcanceEntregaORM, (tenant_id, unidade_id))
    if row is None:
        return None
    return AlcanceEntrega(tenant_id=row.tenant_id, unidade_id=row.unidade_id, limite_km=row.limite_km)


def configurar_alcance(session: Session, alcance: AlcanceEntrega) -> AlcanceEntrega:
    row = session.get(AlcanceEntregaORM, (alcance.tenant_id, alcance.unidade_id))
    if row is None:
        session.add(AlcanceEntregaORM(tenant_id=alcance.tenant_id, unidade_id=alcance.unidade_id, limite_km=alcance.limite_km))
    else:
        row.limite_km = alcance.limite_km
    session.flush()
    return alcance
