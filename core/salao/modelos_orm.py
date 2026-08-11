"""Modelos SQLAlchemy aditivos da operacao de salao V1."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
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


class SalaoBase(DeclarativeBase):
    pass


class MesaORM(SalaoBase):
    __tablename__ = "mesas_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), nullable=False)
    nome: Mapped[str | None] = mapped_column(String(120))
    capacidade: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    posicao_x: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    posicao_y: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "unidade_id", "codigo", name="uq_mesa_codigo_escopo"
        ),
        CheckConstraint("capacidade > 0", name="ck_mesa_capacidade_positiva"),
        CheckConstraint("versao >= 1", name="ck_mesa_versao_positiva"),
        Index("ix_mesa_escopo_status", "tenant_id", "unidade_id", "status"),
        Index("ix_mesa_escopo_ativo", "tenant_id", "unidade_id", "ativo"),
    )


class ComandaORM(SalaoBase):
    __tablename__ = "comandas_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mesa_id: Mapped[str | None] = mapped_column(String(64))
    numero: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    responsavel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    aberta_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    saldo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    recebimento_posterior_autorizado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["mesa_id", "tenant_id", "unidade_id"],
            ["mesas_v1.id", "mesas_v1.tenant_id", "mesas_v1.unidade_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "unidade_id", "numero", name="uq_comanda_numero_escopo"
        ),
        CheckConstraint("total >= 0", name="ck_comanda_total_nao_negativo"),
        CheckConstraint("saldo >= 0", name="ck_comanda_saldo_nao_negativo"),
        CheckConstraint("saldo <= total", name="ck_comanda_saldo_ate_total"),
        CheckConstraint("versao >= 1", name="ck_comanda_versao_positiva"),
        Index("ix_comanda_escopo_mesa", "tenant_id", "unidade_id", "mesa_id"),
        Index("ix_comanda_escopo_status", "tenant_id", "unidade_id", "status"),
    )


class ParticipanteComandaORM(SalaoBase):
    __tablename__ = "comanda_participantes_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    comanda_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cliente_id: Mapped[str | None] = mapped_column(String(64))
    apelido: Mapped[str | None] = mapped_column(String(120))
    quota: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["comanda_id", "tenant_id", "unidade_id"],
            ["comandas_v1.id", "comandas_v1.tenant_id", "comandas_v1.unidade_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "unidade_id", "comanda_id", "ordem",
            name="uq_participante_ordem_comanda",
        ),
        CheckConstraint("ordem > 0", name="ck_participante_ordem_positiva"),
        CheckConstraint("quota IS NULL OR quota >= 0", name="ck_participante_quota_nao_negativa"),
        Index(
            "ix_participante_escopo_comanda", "tenant_id", "unidade_id", "comanda_id"
        ),
    )


class PedidoComandaORM(SalaoBase):
    __tablename__ = "comanda_pedidos_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    comanda_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pedido_id: Mapped[str] = mapped_column(String(64), nullable=False)
    participante_id: Mapped[str | None] = mapped_column(String(64))
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["comanda_id", "tenant_id", "unidade_id"],
            ["comandas_v1.id", "comandas_v1.tenant_id", "comandas_v1.unidade_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "unidade_id", "pedido_id", name="uq_pedido_em_comanda"
        ),
        CheckConstraint("valor >= 0", name="ck_pedido_comanda_valor_nao_negativo"),
        Index("ix_pedido_comanda_escopo", "tenant_id", "unidade_id", "comanda_id"),
    )


class ParcelaFechamentoORM(SalaoBase):
    __tablename__ = "comanda_parcelas_fechamento_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    comanda_id: Mapped[str] = mapped_column(String(64), nullable=False)
    participante_id: Mapped[str | None] = mapped_column(String(64))
    metodo: Mapped[str] = mapped_column(String(40), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["comanda_id", "tenant_id", "unidade_id"],
            ["comandas_v1.id", "comandas_v1.tenant_id", "comandas_v1.unidade_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "unidade_id", "comanda_id", "ordem",
            name="uq_parcela_ordem_comanda",
        ),
        CheckConstraint("valor > 0", name="ck_parcela_valor_positivo"),
        CheckConstraint("ordem > 0", name="ck_parcela_ordem_positiva"),
        Index("ix_parcela_escopo_comanda", "tenant_id", "unidade_id", "comanda_id"),
    )


class PagamentoConfirmadoComandaORM(SalaoBase):
    __tablename__ = "comanda_pagamentos_confirmados_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    comanda_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pagamento_id: Mapped[str] = mapped_column(String(64), nullable=False)
    metodo: Mapped[str] = mapped_column(String(40), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    confirmado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["comanda_id", "tenant_id", "unidade_id"],
            ["comandas_v1.id", "comandas_v1.tenant_id", "comandas_v1.unidade_id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id", "unidade_id", "pagamento_id",
            name="uq_pagamento_confirmado_projecao",
        ),
        UniqueConstraint(
            "tenant_id", "unidade_id", "idempotency_key",
            name="uq_pagamento_comanda_idempotencia",
        ),
        CheckConstraint("valor > 0", name="ck_pagamento_comanda_valor_positivo"),
        Index(
            "ix_pagamento_confirmado_comanda", "tenant_id", "unidade_id", "comanda_id"
        ),
    )


class EventoSalaoORM(SalaoBase):
    __tablename__ = "eventos_salao_v1"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agregado_tipo: Mapped[str] = mapped_column(String(32), nullable=False)
    agregado_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo: Mapped[str] = mapped_column(String(100), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    ator_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_resumo: Mapped[str] = mapped_column(String(2000), nullable=False, default="")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "unidade_id", "idempotency_key",
            name="uq_evento_salao_idempotencia",
        ),
        CheckConstraint("versao >= 1", name="ck_evento_salao_versao_positiva"),
        Index(
            "ix_evento_salao_agregado",
            "tenant_id", "unidade_id", "agregado_tipo", "agregado_id",
        ),
    )
