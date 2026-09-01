"""Schema cifrado de endereços autorizados do Customer Context V1."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

CustomerContextMetadata = MetaData()

Table(
    "crm_clientes_v1",
    CustomerContextMetadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("unidade_id", String(64), primary_key=True),
    Column("cliente_id", String(64), primary_key=True),
)

crm_enderecos_seguros_v1 = Table(
    "crm_enderecos_seguros_v1",
    CustomerContextMetadata,
    Column("referencia", String(128), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("unidade_id", String(64), nullable=False),
    Column("cliente_id", String(64), nullable=False),
    Column("finalidade", String(32), nullable=False),
    Column("valor_hash", String(64), nullable=False),
    Column("ciphertext", Text, nullable=False),
    Column("criado_por", String(64), nullable=False),
    Column("correlation_id", String(128), nullable=False),
    Column("criado_em", DateTime(timezone=True), nullable=False),
    Column("ultimo_uso_em", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ("tenant_id", "unidade_id", "cliente_id"),
        (
            "crm_clientes_v1.tenant_id",
            "crm_clientes_v1.unidade_id",
            "crm_clientes_v1.cliente_id",
        ),
        name="fk_crm_enderecos_cliente_v1",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "tenant_id",
        "unidade_id",
        "cliente_id",
        "finalidade",
        "valor_hash",
        name="uq_crm_endereco_scope_hash_v1",
    ),
    Index(
        "ix_crm_endereco_scope_cliente_v1",
        "tenant_id",
        "unidade_id",
        "cliente_id",
        "finalidade",
        "ultimo_uso_em",
    ),
)
