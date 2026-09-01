"""Schema da autoridade histórica append-only de consentimentos CRM."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
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
)

ConsentimentosCRMMetadata = MetaData()


# Referência mínima necessária para resolução da FK durante DDL.
# crm_clientes_v1 pertence à autoridade canônica Cliente/CRM e não é criada aqui.
Table(
    "crm_clientes_v1",
    ConsentimentosCRMMetadata,
    Column("tenant_id", String(64), primary_key=True),
    Column("unidade_id", String(64), primary_key=True),
    Column("cliente_id", String(64), primary_key=True),
)


# BIGINT em PostgreSQL; INTEGER no SQLite para preservar autoincremento real
# nos testes de integração.
_registro_seq_type = BigInteger().with_variant(Integer, "sqlite")


crm_consentimentos_v1 = Table(
    "crm_consentimentos_v1",
    ConsentimentosCRMMetadata,
    Column(
        "registro_seq",
        _registro_seq_type,
        primary_key=True,
        autoincrement=True,
        nullable=False,
    ),
    Column(
        "consentimento_id",
        String(64),
        nullable=False,
    ),
    Column(
        "tenant_id",
        String(64),
        nullable=False,
    ),
    Column(
        "unidade_id",
        String(64),
        nullable=False,
    ),
    Column(
        "cliente_id",
        String(64),
        nullable=False,
    ),
    Column(
        "canal",
        String(32),
        nullable=False,
    ),
    Column(
        "finalidade",
        String(32),
        nullable=False,
    ),
    Column(
        "status",
        String(32),
        nullable=False,
    ),
    Column(
        "base_legal",
        String(32),
        nullable=False,
    ),
    Column(
        "texto_versao",
        String(128),
        nullable=False,
    ),
    Column(
        "origem",
        String(128),
        nullable=False,
    ),
    Column(
        "prova_hash",
        String(64),
        nullable=False,
    ),
    Column(
        "ocorrido_em",
        DateTime(timezone=True),
        nullable=False,
    ),
    Column(
        "idempotency_key",
        String(128),
        nullable=False,
    ),
    Column(
        "correlation_id",
        String(128),
        nullable=False,
    ),
    Column(
        "concedido_em",
        DateTime(timezone=True),
        nullable=True,
    ),
    Column(
        "revogado_em",
        DateTime(timezone=True),
        nullable=True,
    ),
    ForeignKeyConstraint(
        (
            "tenant_id",
            "unidade_id",
            "cliente_id",
        ),
        (
            "crm_clientes_v1.tenant_id",
            "crm_clientes_v1.unidade_id",
            "crm_clientes_v1.cliente_id",
        ),
        name="fk_crm_consentimentos_cliente_v1",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "tenant_id",
        "unidade_id",
        "consentimento_id",
        name="uq_crm_consentimentos_scope_id_v1",
    ),
    UniqueConstraint(
        "tenant_id",
        "unidade_id",
        "idempotency_key",
        name="uq_crm_consentimentos_scope_idem_v1",
    ),
    CheckConstraint(
        "length(trim(tenant_id)) > 0",
        name="ck_crm_consentimentos_tenant_v1",
    ),
    CheckConstraint(
        "length(trim(unidade_id)) > 0",
        name="ck_crm_consentimentos_unidade_v1",
    ),
    CheckConstraint(
        "length(trim(cliente_id)) > 0",
        name="ck_crm_consentimentos_cliente_v1",
    ),
    CheckConstraint(
        "length(trim(consentimento_id)) > 0",
        name="ck_crm_consentimentos_id_v1",
    ),
    CheckConstraint(
        "canal IN ('whatsapp', 'email', 'sms')",
        name="ck_crm_consentimentos_canal_v1",
    ),
    CheckConstraint(
        "finalidade IN ('promocoes', 'fidelidade')",
        name="ck_crm_consentimentos_finalidade_v1",
    ),
    CheckConstraint(
        "status IN ('concedido', 'revogado')",
        name="ck_crm_consentimentos_status_v1",
    ),
    CheckConstraint(
        "base_legal = 'consentimento'",
        name="ck_crm_consentimentos_base_legal_v1",
    ),
    CheckConstraint(
        "length(prova_hash) = 64",
        name="ck_crm_consentimentos_prova_hash_v1",
    ),
    CheckConstraint(
        "("
        "status = 'concedido' "
        "AND concedido_em IS NOT NULL "
        "AND revogado_em IS NULL"
        ") OR ("
        "status = 'revogado' "
        "AND revogado_em IS NOT NULL"
        ")",
        name="ck_crm_consentimentos_timestamps_v1",
    ),
    Index(
        "ix_crm_consentimentos_cliente_v1",
        "tenant_id",
        "unidade_id",
        "cliente_id",
        "registro_seq",
    ),
    Index(
        "ix_crm_consentimentos_atual_v1",
        "tenant_id",
        "unidade_id",
        "cliente_id",
        "canal",
        "finalidade",
        "ocorrido_em",
        "registro_seq",
    ),
    Index(
        "ix_crm_consentimentos_audiencia_v1",
        "tenant_id",
        "unidade_id",
        "canal",
        "finalidade",
        "ocorrido_em",
        "registro_seq",
    ),
)
