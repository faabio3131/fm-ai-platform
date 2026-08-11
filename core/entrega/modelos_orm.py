"""Persistência aditiva da Expedição e Entrega V1.

As tabelas deste módulo só são materializadas pelo runtime de teste da PR13.
Não há migration de produção nesta etapa.
"""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DeliveryBase(DeclarativeBase):
    pass


class EntregaORM(DeliveryBase):
    __tablename__ = "entregas_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    endereco_id: Mapped[str] = mapped_column(String(64), nullable=False)
    modalidade: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    tentativa: Mapped[int] = mapped_column(Integer, nullable=False)
    entregador_id: Mapped[str | None] = mapped_column(String(64))
    producao_pronta_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    checklist_concluido_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    atribuida_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    coletada_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    saiu_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    entregue_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    prova_entrega_ref: Mapped[str | None] = mapped_column(String(255))
    atualizado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "pedido_id",
            name="uq_entrega_pedido_escopo",
        ),
        CheckConstraint("versao >= 1", name="ck_entrega_versao"),
        CheckConstraint("tentativa >= 1", name="ck_entrega_tentativa"),
        Index("ix_entrega_escopo_status", "tenant_id", "unidade_id", "status"),
        Index(
            "ix_entrega_escopo_entregador",
            "tenant_id",
            "unidade_id",
            "entregador_id",
            "status",
        ),
    )


class EventoEntregaORM(DeliveryBase):
    __tablename__ = "eventos_entrega_v1"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entrega_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    ator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ocorrido_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    versao_entrega: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_seguro: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_evento_entrega_idempotencia",
        ),
        CheckConstraint("versao_entrega >= 1", name="ck_evento_entrega_versao"),
        Index(
            "ix_evento_entrega_escopo_agregado",
            "tenant_id",
            "unidade_id",
            "entrega_id",
            "ocorrido_em",
        ),
    )
