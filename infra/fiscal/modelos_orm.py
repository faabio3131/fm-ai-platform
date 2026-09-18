"""SQLAlchemy persistence schema for Kordena Fiscal V1 integration."""

from __future__ import annotations

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class FiscalBase(DeclarativeBase):
    pass


class FiscalSequenceORM(FiscalBase):
    __tablename__ = "fiscal_sequences_v1"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[int] = mapped_column(Integer, primary_key=True)
    series: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_number: Mapped[int] = mapped_column(Integer, nullable=False)
    max_number: Mapped[int | None] = mapped_column(Integer)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FiscalIdempotencyORM(FiscalBase):
    __tablename__ = "fiscal_idempotency_v1"

    key_value: Mapped[str] = mapped_column(String(64), primary_key=True)
    generation: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_reference: Mapped[str | None] = mapped_column(String(512))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        Index("ix_fiscal_idempotency_key_generation", "key_value", "generation"),
    )


class FiscalOutboxORM(FiscalBase):
    __tablename__ = "fiscal_outbox_v1"

    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    operation: Mapped[str] = mapped_column(String(128), nullable=False)
    deduplication_key: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    available_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_until: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    completion_reference: Mapped[str | None] = mapped_column(String(512))
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "operation",
            "deduplication_key",
            name="uq_fiscal_outbox_dedup_v1",
        ),
        Index("ix_fiscal_outbox_due_v1", "status", "available_at"),
        Index("ix_fiscal_outbox_scope_v1", "tenant_id", "unit_id", "environment"),
    )


class FiscalArchiveORM(FiscalBase):
    __tablename__ = "fiscal_archive_v1"

    entry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    document_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    archived_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    retention_policy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    retention_policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    retain_until: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    legal_basis_reference: Mapped[str | None] = mapped_column(String(512))
    previous_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        Index(
            "ix_fiscal_archive_document_v1",
            "tenant_id",
            "unit_id",
            "environment",
            "document_reference",
            "archived_at",
        ),
    )


class FiscalDocumentProjectionORM(FiscalBase):
    __tablename__ = "fiscal_document_projection_v1"

    document_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False)
    document_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    access_key: Mapped[str | None] = mapped_column(String(64))
    protocol_reference: Mapped[str | None] = mapped_column(String(512))
    rejection_code: Mapped[str | None] = mapped_column(String(64))
    rejection_message: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "source_type",
            "source_id",
            "document_kind",
            name="uq_fiscal_projection_source_v1",
        ),
        Index("ix_fiscal_projection_scope_state_v1", "tenant_id", "unit_id", "state"),
    )


class FiscalInboundDocumentORM(FiscalBase):
    __tablename__ = "fiscal_inbound_documents_v1"

    inbound_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    access_key: Mapped[str] = mapped_column(String(64), nullable=False)
    nsu: Mapped[str | None] = mapped_column(String(32))
    issuer_document: Mapped[str | None] = mapped_column(String(32))
    issuer_name: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    xml_content: Mapped[bytes | None] = mapped_column(LargeBinary)
    xml_sha256: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    discovered_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "access_key",
            name="uq_fiscal_inbound_access_key_v1",
        ),
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "nsu",
            name="uq_fiscal_inbound_nsu_v1",
        ),
        Index("ix_fiscal_inbound_scope_status_v1", "tenant_id", "unit_id", "status"),
    )


class FiscalDfeCheckpointORM(FiscalBase):
    __tablename__ = "fiscal_dfe_checkpoint_v1"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    recipient_document: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_nsu: Mapped[str] = mapped_column(String(32), nullable=False)
    max_nsu: Mapped[str | None] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)


class FiscalManifestationORM(FiscalBase):
    __tablename__ = "fiscal_manifestations_v1"

    manifestation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    access_key: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    protocol_reference: Mapped[str | None] = mapped_column(String(512))
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "idempotency_key",
            name="uq_fiscal_manifestation_idempotency_v1",
        ),
        Index("ix_fiscal_manifestation_document_v1", "tenant_id", "unit_id", "access_key"),
    )


class FiscalProductBindingORM(FiscalBase):
    __tablename__ = "fiscal_product_bindings_v1"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class FiscalIssuerProfileORM(FiscalBase):
    __tablename__ = "fiscal_issuer_profiles_v1"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    certificate_reference: Mapped[str | None] = mapped_column(String(256))
    provider_config_id: Mapped[str | None] = mapped_column(String(256))
    valid_from: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[object | None] = mapped_column(DateTime(timezone=True))
