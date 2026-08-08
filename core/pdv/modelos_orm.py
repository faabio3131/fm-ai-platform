"""Persistencia aditiva de vinculos, efeitos idempotentes e reconciliacao."""

from sqlalchemy import DateTime, Index, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PDVBase(DeclarativeBase):
    pass


class EfeitoCompatPDVORM(PDVBase):
    __tablename__ = "pdv_efeitos_compat_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo_efeito: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    referencia_legada: Mapped[str | None] = mapped_column(String(64))
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "pedido_id",
            "tipo_efeito",
            name="uq_pdv_efeito_economico",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_pdv_efeito_idempotencia",
        ),
    )


class VendaLegadaLinkORM(PDVBase):
    __tablename__ = "pdv_venda_legada_links_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    venda_financeira_id: Mapped[str] = mapped_column(String(64), nullable=False)
    venda_legada_id: Mapped[str] = mapped_column(String(64), nullable=False)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "unidade_id", "pedido_id", name="uq_pdv_link_pedido"
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "venda_financeira_id",
            name="uq_pdv_link_venda_financeira",
        ),
        UniqueConstraint("venda_legada_id", name="uq_pdv_link_venda_legada"),
    )


class ReconciliacaoPDVORM(PDVBase):
    __tablename__ = "pdv_reconciliacoes_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    modo: Mapped[str] = mapped_column(String(30), nullable=False)
    pedido_id: Mapped[str | None] = mapped_column(String(64))
    pagamento_id: Mapped[str | None] = mapped_column(String(64))
    venda_financeira_id: Mapped[str | None] = mapped_column(String(64))
    venda_legada_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    valor_pedido: Mapped[object | None] = mapped_column(Numeric(14, 2))
    valor_pagamento: Mapped[object | None] = mapped_column(Numeric(14, 2))
    valor_venda_financeira: Mapped[object | None] = mapped_column(Numeric(14, 2))
    valor_venda_legada: Mapped[object | None] = mapped_column(Numeric(14, 2))
    estoque_estrategia: Mapped[str] = mapped_column(String(30), nullable=False)
    cashback_usado: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    cashback_ganho: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    divergencias: Mapped[list] = mapped_column(JSON, nullable=False)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_pdv_reconciliacao_checkout",
        ),
        Index("ix_pdv_reconciliacao_status", "tenant_id", "unidade_id", "status"),
    )
