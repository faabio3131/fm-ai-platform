"""Tabelas exclusivamente aditivas do ledger de estoque V1."""

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class StockBase(DeclarativeBase):
    pass


class MovimentoEstoqueORM(StockBase):
    __tablename__ = "estoque_ledger_v1"
    movimento_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    insumo_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo_movimento: Mapped[str] = mapped_column(String(32), nullable=False)
    quantidade: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False)
    unidade_medida: Mapped[str] = mapped_column(String(24), nullable=False)
    origem_tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    origem_id: Mapped[str] = mapped_column(String(64), nullable=False)
    origem_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(64))
    ator: Mapped[str] = mapped_column(String(64), nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(500))
    metadata_segura: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="ck_estoque_ledger_quantidade_positiva"),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_estoque_ledger_idempotencia",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "origem_tipo",
            "origem_id",
            "tipo_movimento",
            "insumo_id",
            "origem_versao",
            name="uq_estoque_ledger_movimento_logico",
        ),
        Index(
            "ix_estoque_ledger_escopo_insumo_ordem",
            "tenant_id",
            "unidade_id",
            "insumo_id",
            "occurred_at",
            "movimento_id",
        ),
        Index(
            "ix_estoque_ledger_escopo_origem",
            "tenant_id",
            "unidade_id",
            "origem_tipo",
            "origem_id",
        ),
    )


class SaldoEstoqueORM(StockBase):
    __tablename__ = "estoque_saldos_v1"
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    insumo_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    saldo_fisico: Mapped[object] = mapped_column(
        Numeric(18, 6), nullable=False, default=0
    )
    saldo_reservado: Mapped[object] = mapped_column(
        Numeric(18, 6), nullable=False, default=0
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        CheckConstraint(
            "saldo_reservado >= 0", name="ck_estoque_saldo_reservado_nao_negativo"
        ),
        Index("ix_estoque_saldo_escopo", "tenant_id", "unidade_id", "insumo_id"),
    )


class ReservaEstoqueORM(StockBase):
    __tablename__ = "estoque_reservas_v1"
    reserva_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_versao: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    criada_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    resolvida_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "unidade_id", "pedido_id", name="uq_estoque_reserva_pedido"
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_estoque_reserva_idempotencia",
        ),
        Index("ix_estoque_reserva_escopo_status", "tenant_id", "unidade_id", "status"),
    )
