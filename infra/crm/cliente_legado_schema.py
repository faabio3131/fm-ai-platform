"""Schema da ponte governada entre Cliente legado e ClienteCRM."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    func,
)

ClienteLegadoMappingMetadata = MetaData()


# Referências mínimas necessárias para resolução das FKs durante DDL.
# Estas tabelas pertencem a outros domínios e não são criadas por este módulo.
Table(
    "clientes",
    ClienteLegadoMappingMetadata,
    Column("id", Integer, primary_key=True),
)

Table(
    "crm_clientes_v1",
    ClienteLegadoMappingMetadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("unidade_id", String(64), primary_key=True),
    Column("cliente_id", String(64), primary_key=True),
)


crm_cliente_legado_v1 = Table(
    "crm_cliente_legado_v1",
    ClienteLegadoMappingMetadata,
    Column(
        "tenant_id",
        String(64),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "unidade_id",
        String(64),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "legacy_cliente_id",
        Integer,
        primary_key=True,
        nullable=False,
    ),
    Column(
        "cliente_id",
        String(64),
        nullable=False,
    ),
    Column(
        "criado_por",
        String(64),
        nullable=False,
    ),
    Column(
        "correlation_id",
        String(128),
        nullable=False,
    ),
    Column(
        "criado_em",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    ForeignKeyConstraint(
        ["legacy_cliente_id"],
        ["clientes.id"],
        name="fk_crm_cliente_legado_cliente_v1",
        ondelete="RESTRICT",
    ),
    ForeignKeyConstraint(
        [
            "tenant_id",
            "unidade_id",
            "cliente_id",
        ],
        [
            "crm_clientes_v1.tenant_id",
            "crm_clientes_v1.unidade_id",
            "crm_clientes_v1.cliente_id",
        ],
        name="fk_crm_cliente_legado_canonico_v1",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "legacy_cliente_id",
        name="uq_crm_cliente_legado_legacy_id_v1",
    ),
    UniqueConstraint(
        "tenant_id",
        "unidade_id",
        "cliente_id",
        name="uq_crm_cliente_legado_scope_cliente_v1",
    ),
    CheckConstraint(
        "length(trim(tenant_id)) > 0",
        name="ck_crm_cliente_legado_tenant_v1",
    ),
    CheckConstraint(
        "length(trim(unidade_id)) > 0",
        name="ck_crm_cliente_legado_unidade_v1",
    ),
    CheckConstraint(
        "length(trim(cliente_id)) > 0",
        name="ck_crm_cliente_legado_cliente_id_v1",
    ),
    CheckConstraint(
        "length(trim(criado_por)) > 0",
        name="ck_crm_cliente_legado_criado_por_v1",
    ),
    CheckConstraint(
        "length(trim(correlation_id)) > 0",
        name="ck_crm_cliente_legado_correlation_v1",
    ),
    Index(
        "ix_crm_cliente_legado_scope_v1",
        "tenant_id",
        "unidade_id",
    ),
)
