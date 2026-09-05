"""Schema canônico do ledger de cashback CRM V1."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData()

crm_cashback_saldos_v1 = Table(
    "crm_cashback_saldos_v1",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("unidade_id", String(64), primary_key=True),
    Column("cliente_id", String(64), primary_key=True),
    Column("saldo", Numeric(18, 2), nullable=False),
    Column("versao", Integer, nullable=False),
    ForeignKeyConstraint(
        ["tenant_id", "unidade_id", "cliente_id"],
        [
            "crm_clientes_v1.tenant_id",
            "crm_clientes_v1.unidade_id",
            "crm_clientes_v1.cliente_id",
        ],
        name="fk_crm_cashback_saldos_cliente_v1",
        ondelete="CASCADE",
    ),
    CheckConstraint("saldo >= 0", name="ck_crm_cashback_saldo_nao_negativo_v1"),
    CheckConstraint("versao >= 0", name="ck_crm_cashback_saldo_versao_v1"),
)

crm_cashback_movimentos_v1 = Table(
    "crm_cashback_movimentos_v1",
    metadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("unidade_id", String(64), primary_key=True),
    Column("movimento_id", String(64), primary_key=True),
    Column("cliente_id", String(64), nullable=False),
    Column("tipo", String(16), nullable=False),
    Column("valor", Numeric(18, 2), nullable=False),
    Column("origem", String(64), nullable=False),
    Column("referencia", String(256), nullable=False),
    Column("ocorrido_em", DateTime(timezone=True), nullable=False),
    Column("idempotency_key", String(256), nullable=False),
    ForeignKeyConstraint(
        ["tenant_id", "unidade_id", "cliente_id"],
        [
            "crm_clientes_v1.tenant_id",
            "crm_clientes_v1.unidade_id",
            "crm_clientes_v1.cliente_id",
        ],
        name="fk_crm_cashback_movimentos_cliente_v1",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "tenant_id",
        "unidade_id",
        "idempotency_key",
        name="uq_crm_cashback_movimentos_idem_v1",
    ),
    CheckConstraint(
        "tipo IN ('credito', 'debito')",
        name="ck_crm_cashback_movimento_tipo_v1",
    ),
    CheckConstraint("valor > 0", name="ck_crm_cashback_movimento_valor_v1"),
)

Index(
    "ix_crm_cashback_movimentos_cliente_v1",
    crm_cashback_movimentos_v1.c.tenant_id,
    crm_cashback_movimentos_v1.c.unidade_id,
    crm_cashback_movimentos_v1.c.cliente_id,
    crm_cashback_movimentos_v1.c.ocorrido_em,
    crm_cashback_movimentos_v1.c.movimento_id,
)
