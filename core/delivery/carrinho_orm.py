"""Persistência comercial do estado do carrinho Delivery Próprio V1."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DeliveryChannelBase(DeclarativeBase):
    pass


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class CarrinhoDeliveryORM(DeliveryChannelBase):
    __tablename__ = "delivery_carrinhos_v1"
    __table_args__ = (
        CheckConstraint("versao >= 1", name="ck_delivery_carrinho_versao_v1"),
        Index(
            "ix_delivery_carrinhos_cliente_v1",
            "tenant_id",
            "unidade_id",
            "cliente_ref",
            "status",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    carrinho_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    cliente_ref: Mapped[str] = mapped_column(String(96), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora, onupdate=_agora
    )
