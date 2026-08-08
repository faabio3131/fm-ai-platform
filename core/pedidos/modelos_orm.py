"""Modelos SQLAlchemy exclusivos das novas tabelas de Pedido."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class OrdersBase(DeclarativeBase):
    pass


class PedidoORM(OrdersBase):
    __tablename__ = "pedidos_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    origem: Mapped[str] = mapped_column(String(40), nullable=False)
    canal: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    cliente_id: Mapped[str | None] = mapped_column(String(64))
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    subtotal: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    descontos: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    taxas: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    itens: Mapped[list["ItemPedidoORM"]] = relationship(
        cascade="all, delete-orphan", order_by="ItemPedidoORM.ordem"
    )
    observacoes: Mapped[list["ObservacaoPedidoORM"]] = relationship(
        cascade="all, delete-orphan", order_by="ObservacaoPedidoORM.ordem"
    )
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_pedido_idempotencia_escopo",
        ),
        CheckConstraint("versao >= 1", name="ck_pedido_versao_positiva"),
        Index("ix_pedido_escopo_id", "tenant_id", "unidade_id", "id"),
        Index("ix_pedido_escopo_status", "tenant_id", "unidade_id", "status"),
        Index("ix_pedido_escopo_criado", "tenant_id", "unidade_id", "criado_em"),
        Index(
            "ix_pedido_escopo_idempotencia",
            "tenant_id",
            "unidade_id",
            "idempotency_key",
        ),
    )


class ItemPedidoORM(OrdersBase):
    __tablename__ = "itens_pedido_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    produto_id: Mapped[str | None] = mapped_column(String(64))
    nome_produto: Mapped[str] = mapped_column(String(255), nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_unitario: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    subtotal: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text)
    ficha_versao: Mapped[str | None] = mapped_column(String(64))
    adicionais: Mapped[list["AdicionalItemPedidoORM"]] = relationship(
        cascade="all, delete-orphan", order_by="AdicionalItemPedidoORM.ordem"
    )
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "pedido_id"],
            ["pedidos_v1.tenant_id", "pedidos_v1.unidade_id", "pedidos_v1.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "unidade_id", "pedido_id", "ordem", name="uq_item_ordem_pedido"
        ),
        CheckConstraint("quantidade > 0", name="ck_item_quantidade_positiva"),
        Index("ix_item_escopo_pedido", "tenant_id", "unidade_id", "pedido_id"),
    )


class AdicionalItemPedidoORM(OrdersBase):
    __tablename__ = "adicionais_item_pedido_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    preco_unitario: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    subtotal: Mapped[object] = mapped_column(Numeric(14, 2), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "item_id"],
            [
                "itens_pedido_v1.tenant_id",
                "itens_pedido_v1.unidade_id",
                "itens_pedido_v1.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "item_id",
            "ordem",
            name="uq_adicional_ordem_item",
        ),
        Index("ix_adicional_escopo_item", "tenant_id", "unidade_id", "item_id"),
    )


class ObservacaoPedidoORM(OrdersBase):
    __tablename__ = "observacoes_pedido_v1"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "pedido_id"],
            ["pedidos_v1.tenant_id", "pedidos_v1.unidade_id", "pedidos_v1.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_observacao_escopo_pedido", "tenant_id", "unidade_id", "pedido_id"),
    )


class EventoPedidoPersistidoORM(OrdersBase):
    __tablename__ = "eventos_pedido_v1"
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "pedido_id"],
            ["pedidos_v1.tenant_id", "pedidos_v1.unidade_id", "pedidos_v1.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_evento_pedido_idempotencia",
        ),
        Index("ix_evento_escopo_pedido", "tenant_id", "unidade_id", "pedido_id"),
    )
