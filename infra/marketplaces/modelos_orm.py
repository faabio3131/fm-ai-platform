"""Persistência do vínculo Marketplace -> Pedido canônico para a V1 Web."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class MarketplaceBase(DeclarativeBase):
    pass


class PedidoExternoMarketplaceORM(MarketplaceBase):
    __tablename__ = "fm_marketplace_pedidos_externos_v1"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "integracao_id",
            "id_externo",
            name="uq_fm_marketplace_pedido_externo_v1",
        ),
        Index(
            "ix_fm_marketplace_pedido_scope_v1",
            "tenant_id",
            "unidade_id",
            "integracao_id",
        ),
        Index(
            "ix_fm_marketplace_pedido_interno_v1",
            "tenant_id",
            "unidade_id",
            "pedido_id",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    integracao_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    id_externo: Mapped[str] = mapped_column(String(160), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status_externo: Mapped[str] = mapped_column(String(40), nullable=False)
    status_interno: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    recebido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ultima_ocorrencia_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ultimo_evento_id: Mapped[str] = mapped_column(String(128), nullable=False)
    versao_externa: Mapped[str | None] = mapped_column(String(128))
