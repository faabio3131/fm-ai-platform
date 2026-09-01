"""Migration 0029 — autoridade canônica de destinatários internos tenant-scoped."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
)
from sqlalchemy.engine import Connection


TABLE_NAME = "notificacao_interna_destinatarios_v1"


def upgrade_internal_notification_recipients_v1(connection: Connection) -> None:
    """Cria a autoridade canônica sem realizar backfill do legado global."""

    metadata = MetaData()
    destinatarios = Table(
        TABLE_NAME,
        metadata,
        Column("destinatario_id", String(64), primary_key=True),
        Column("tenant_id", String(64), nullable=False),
        Column("unidade_id", String(64), nullable=False),
        Column("nome_exibicao", String(120), nullable=False),
        Column("cargo", String(80), nullable=True),
        Column("canal", String(32), nullable=False),
        Column("referencia_contato", String(128), nullable=False),
        Column("contato_fingerprint", String(64), nullable=False),
        Column("contato_ciphertext", Text, nullable=False),
        Column("contato_mascara", String(32), nullable=False),
        Column("receber_alertas_estoque", Boolean, nullable=False),
        Column("ativo", Boolean, nullable=False),
        Column("versao", Integer, nullable=False),
        Column("criado_por", String(64), nullable=False),
        Column("atualizado_por", String(64), nullable=False),
        Column("correlation_id", String(128), nullable=False),
        Column("criado_em", DateTime(timezone=True), nullable=False),
        Column("atualizado_em", DateTime(timezone=True), nullable=False),
        UniqueConstraint(
            "referencia_contato",
            name="uq_notificacao_interna_referencia_v1",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "canal",
            "contato_fingerprint",
            name="uq_notificacao_interna_scope_contato_v1",
        ),
        Index(
            "ix_notificacao_interna_scope_alerta_v1",
            "tenant_id",
            "unidade_id",
            "ativo",
            "receber_alertas_estoque",
        ),
    )

    inspector = inspect(connection)
    if TABLE_NAME not in inspector.get_table_names():
        destinatarios.create(bind=connection, checkfirst=True)

    inspector = inspect(connection)
    required = {
        "destinatario_id",
        "tenant_id",
        "unidade_id",
        "nome_exibicao",
        "cargo",
        "canal",
        "referencia_contato",
        "contato_fingerprint",
        "contato_ciphertext",
        "contato_mascara",
        "receber_alertas_estoque",
        "ativo",
        "versao",
        "criado_por",
        "atualizado_por",
        "correlation_id",
        "criado_em",
        "atualizado_em",
    }
    existing = {
        str(column["name"])
        for column in inspector.get_columns(TABLE_NAME)
    }
    if existing != required:
        raise RuntimeError(
            "notificacao_interna_destinatarios_v1 possui schema divergente"
        )

    indexes = {
        str(index.get("name") or ""): (
            tuple(str(column) for column in index.get("column_names") or ()),
            bool(index.get("unique")),
        )
        for index in inspector.get_indexes(TABLE_NAME)
    }
    expected_index = (
        ("tenant_id", "unidade_id", "ativo", "receber_alertas_estoque"),
        False,
    )
    if indexes.get("ix_notificacao_interna_scope_alerta_v1") != expected_index:
        raise RuntimeError(
            "indice scoped de notificacoes internas ausente ou divergente"
        )
