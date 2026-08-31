"""Persistência aditiva do Core/Gerente IA e do Assistente de Atendimento V1."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CoreRuntimeBase(DeclarativeBase):
    pass


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class IdentidadeAssistenteORM(CoreRuntimeBase):
    __tablename__ = "assistente_atendimento_identidade_v1"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nome_publico: Mapped[str] = mapped_column(String(80), nullable=False)
    atributos: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    atualizado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_agora)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_agora)


class EventoCoreORM(CoreRuntimeBase):
    __tablename__ = "gerente_ia_eventos_v1"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unidade_id", "idempotency_key", name="uq_core_evento_idem_v1"),
        Index("ix_core_evento_scope_time_v1", "tenant_id", "unidade_id", "ocorrido_em"),
        Index("ix_core_evento_corr_v1", "tenant_id", "unidade_id", "correlation_id"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(192), nullable=False)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_seguro: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    processado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_agora)


class PreviewGerenteIAORM(CoreRuntimeBase):
    __tablename__ = "gerente_ia_previews_v1"
    __table_args__ = (Index("ix_core_preview_scope_v1", "tenant_id", "unidade_id", "status"),)

    preview_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    recurso_id: Mapped[str] = mapped_column(String(128), nullable=False)
    argumentos: Mapped[dict] = mapped_column(JSON, nullable=False)
    impacto_tipo: Mapped[str] = mapped_column(String(96), nullable=False)
    impacto_campos: Mapped[dict] = mapped_column(JSON, nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    criado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ResultadoAcaoGerenteIAORM(CoreRuntimeBase):
    __tablename__ = "gerente_ia_resultados_acao_v1"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unidade_id", "idempotency_key", name="uq_core_resultado_idem_v1"),
    )

    resultado_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_id: Mapped[str] = mapped_column(String(96), nullable=False)
    tool: Mapped[str] = mapped_column(String(64), nullable=False)
    recurso_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resultado: Mapped[str] = mapped_column(Text, nullable=False)
    executado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    executado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(192), nullable=False)


class DisponibilidadeProdutoORM(CoreRuntimeBase):
    __tablename__ = "produto_disponibilidade_v1"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    produto_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pausado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pausado_ate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str | None] = mapped_column(Text)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    atualizado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_agora)


class ClienteCRMORM(CoreRuntimeBase):
    __tablename__ = "crm_clientes_v1"
    __table_args__ = (
        CheckConstraint(
            "versao >= 1",
            name="ck_crm_clientes_versao_v1",
        ),
        Index(
            "ix_crm_clientes_scope_v1",
            "tenant_id",
            "unidade_id",
            "criado_em",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cliente_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    origem: Mapped[str] = mapped_column(String(32), nullable=False)
    marketplace_origem: Mapped[str | None] = mapped_column(String(32), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class ContatoCRMORM(CoreRuntimeBase):
    __tablename__ = "crm_cliente_contatos_v1"
    __table_args__ = (
        ForeignKeyConstraint(
            ("tenant_id", "unidade_id", "cliente_id"),
            (
                "crm_clientes_v1.tenant_id",
                "crm_clientes_v1.unidade_id",
                "crm_clientes_v1.cliente_id",
            ),
            name="fk_crm_cliente_contatos_cliente_v1",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "referencia LIKE 'contact://%' OR referencia LIKE 'vault://%'",
            name="ck_crm_cliente_contato_referencia_v1",
        ),
        Index(
            "ix_crm_cliente_contatos_scope_v1",
            "tenant_id",
            "unidade_id",
            "cliente_id",
        ),
        Index(
            "uq_crm_cliente_contato_scope_ref_owner_v1",
            "tenant_id",
            "unidade_id",
            "referencia",
            unique=True,
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cliente_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canal: Mapped[str] = mapped_column(String(32), primary_key=True)
    referencia: Mapped[str] = mapped_column(String(512), nullable=False)


class ConsentimentoCRMAtualORM(CoreRuntimeBase):
    __tablename__ = "crm_consentimentos_atuais_v1"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cliente_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    canal: Mapped[str] = mapped_column(String(32), primary_key=True)
    finalidade: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)


class RascunhoCampanhaORM(CoreRuntimeBase):
    __tablename__ = "crm_rascunhos_campanha_v1"
    __table_args__ = (
        UniqueConstraint("tenant_id", "unidade_id", "idempotency_key", name="uq_crm_rascunho_idem_v1"),
        Index("ix_crm_rascunho_scope_v1", "tenant_id", "unidade_id", "criado_em"),
    )

    rascunho_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    canal: Mapped[str] = mapped_column(String(32), nullable=False)
    finalidade: Mapped[str] = mapped_column(String(64), nullable=False)
    objetivo: Mapped[str] = mapped_column(String(240), nullable=False)
    texto_base: Mapped[str] = mapped_column(Text, nullable=False)
    audiencia_elegivel: Mapped[int] = mapped_column(Integer, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    criado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(192), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="rascunho")
