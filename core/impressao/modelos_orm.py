"""Modelos SQLAlchemy aditivos do spool de impressão V1."""

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ImpressaoBase(DeclarativeBase):
    pass


class JobImpressaoORM(ImpressaoBase):
    __tablename__ = "impressao_jobs_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    setor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    producao_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    impressora_id: Mapped[str] = mapped_column(String(128), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    documento_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    tentativa: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ultimo_erro: Mapped[str | None] = mapped_column(String(80))
    reimpressao_de: Mapped[str | None] = mapped_column(String(64))
    motivo_reimpressao: Mapped[str | None] = mapped_column(String(180))

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "dedup_key",
            name="uq_impressao_dedup_escopo",
        ),
        CheckConstraint("tentativa >= 0", name="ck_impressao_tentativa_nao_negativa"),
        CheckConstraint(
            "max_tentativas >= 1 AND max_tentativas <= 10",
            name="ck_impressao_max_tentativas",
        ),
        CheckConstraint("versao >= 1", name="ck_impressao_versao_positiva"),
        CheckConstraint(
            "tentativa <= max_tentativas",
            name="ck_impressao_tentativa_limite",
        ),
        Index(
            "ix_impressao_spool_status",
            "tenant_id",
            "unidade_id",
            "status",
            "criado_em",
        ),
        Index(
            "ix_impressao_setor",
            "tenant_id",
            "unidade_id",
            "setor_id",
            "criado_em",
        ),
    )
