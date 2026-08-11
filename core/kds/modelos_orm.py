"""Modelos SQLAlchemy aditivos do KDS V1."""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class KDSBase(DeclarativeBase):
    pass


class SetorProducaoORM(KDSBase):
    __tablename__ = "setores_producao_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(80), nullable=False)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sla_segundos: Mapped[int | None] = mapped_column(Integer)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "codigo",
            name="uq_kds_setor_codigo_escopo",
        ),
        CheckConstraint("ordem >= 0", name="ck_kds_setor_ordem"),
        CheckConstraint(
            "sla_segundos IS NULL OR sla_segundos > 0", name="ck_kds_setor_sla"
        ),
        Index("ix_kds_setor_escopo_ordem", "tenant_id", "unidade_id", "ordem"),
        Index("ix_kds_setor_escopo_ativo", "tenant_id", "unidade_id", "ativo"),
    )


class ProducaoItemORM(KDSBase):
    __tablename__ = "producao_itens_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    setor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    prioridade: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quantidade: Mapped[object] = mapped_column(Numeric(14, 4), nullable=False)
    tentativa: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    aceita_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    iniciada_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    pausa_iniciada_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    pronta_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    retirada_em: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    responsavel_id: Mapped[str | None] = mapped_column(String(64))
    pausa_acumulada_segundos: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "setor_id"],
            [
                "setores_producao_v1.tenant_id",
                "setores_producao_v1.unidade_id",
                "setores_producao_v1.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "pedido_item_id",
            "setor_id",
            "tentativa",
            name="uq_kds_item_setor_tentativa",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_kds_roteamento_idempotencia",
        ),
        CheckConstraint("quantidade > 0", name="ck_kds_quantidade_positiva"),
        CheckConstraint("tentativa >= 1", name="ck_kds_tentativa_positiva"),
        CheckConstraint("versao >= 1", name="ck_kds_versao_positiva"),
        CheckConstraint(
            "pausa_acumulada_segundos >= 0", name="ck_kds_pausa_nao_negativa"
        ),
        Index(
            "ix_kds_fila_setor",
            "tenant_id",
            "unidade_id",
            "setor_id",
            "status",
            "prioridade",
            "criado_em",
        ),
        Index("ix_kds_pedido", "tenant_id", "unidade_id", "pedido_id"),
        Index("ix_kds_pedido_item", "tenant_id", "unidade_id", "pedido_item_id"),
    )


class EventoProducaoORM(KDSBase):
    __tablename__ = "eventos_producao_v1"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    producao_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    ocorrido_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "unidade_id", "producao_item_id"],
            [
                "producao_itens_v1.tenant_id",
                "producao_itens_v1.unidade_id",
                "producao_itens_v1.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "idempotency_key",
            name="uq_kds_evento_idempotencia",
        ),
        Index(
            "ix_kds_evento_item",
            "tenant_id",
            "unidade_id",
            "producao_item_id",
            "ocorrido_em",
        ),
    )
