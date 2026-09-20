"""Application boundary for Fiscal V1 inbound documents and DF-e distribution."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from kordena_fiscal.domain import Cnpj, ExecutionScope, FiscalValidationError
from kordena_fiscal.inbound import (
    DfeDistributionBatch,
    FiscalInboundDocument,
    FiscalInboundSource,
    FiscalManifestation,
    FiscalManifestationType,
    FiscalNsuCheckpoint,
    parse_nfe_xml,
)
from kordena_fiscal.xml import NfeAccessKey


class FiscalDfeDistributionAdapter(Protocol):
    """Provider-neutral boundary. Concrete SEFAZ/provider wiring belongs to WP-031I."""

    def distribute(
        self,
        *,
        scope: ExecutionScope,
        recipient_document: Cnpj,
        after_nsu: str,
    ) -> DfeDistributionBatch: ...


class FiscalInboundStore(Protocol):
    def save_upload(
        self,
        document: FiscalInboundDocument,
    ) -> tuple[FiscalInboundDocument, bool]: ...

    def save_distribution(
        self,
        *,
        scope: ExecutionScope,
        recipient_document: Cnpj,
        documents: tuple[FiscalInboundDocument, ...],
        last_nsu: str,
        max_nsu: str,
        updated_at: datetime,
    ) -> tuple[tuple[FiscalInboundDocument, ...], FiscalNsuCheckpoint]: ...

    def checkpoint(
        self,
        *,
        scope: ExecutionScope,
        recipient_document: Cnpj,
    ) -> FiscalNsuCheckpoint | None: ...

    def list_inbox(
        self,
        *,
        scope: ExecutionScope,
        limit: int = 100,
    ) -> tuple[FiscalInboundDocument, ...]: ...

    def record_manifestation(self, manifestation: FiscalManifestation) -> bool: ...


class FiscalInboundApplication:
    """Coordinates authoritative XML ingestion without stock or financial effects."""

    def __init__(self, *, store: FiscalInboundStore) -> None:
        self._store = store

    def synchronize_dfe(
        self,
        *,
        scope: ExecutionScope,
        recipient_document: Cnpj,
        adapter: FiscalDfeDistributionAdapter,
    ) -> tuple[tuple[FiscalInboundDocument, ...], FiscalNsuCheckpoint]:
        current = self._store.checkpoint(
            scope=scope,
            recipient_document=recipient_document,
        )
        after_nsu = "000000000000000" if current is None else current.last_nsu
        batch = adapter.distribute(
            scope=scope,
            recipient_document=recipient_document,
            after_nsu=after_nsu,
        )
        if not isinstance(batch, DfeDistributionBatch):
            raise FiscalValidationError(
                "DF-e adapter must return DfeDistributionBatch"
            )
        documents = tuple(
            parse_nfe_xml(
                scope=scope,
                recipient_document=recipient_document,
                xml_content=entry.xml_content,
                source=FiscalInboundSource.DFE,
                discovered_at=batch.fetched_at,
                nsu=entry.nsu,
            )
            for entry in batch.entries
        )
        return self._store.save_distribution(
            scope=scope,
            recipient_document=recipient_document,
            documents=documents,
            last_nsu=batch.last_nsu,
            max_nsu=batch.max_nsu,
            updated_at=batch.fetched_at,
        )

    def ingest_xml_upload(
        self,
        *,
        scope: ExecutionScope,
        recipient_document: Cnpj,
        xml_content: bytes,
        received_at: datetime,
    ) -> tuple[FiscalInboundDocument, bool]:
        document = parse_nfe_xml(
            scope=scope,
            recipient_document=recipient_document,
            xml_content=xml_content,
            source=FiscalInboundSource.XML_UPLOAD,
            discovered_at=received_at,
        )
        return self._store.save_upload(document)

    def list_inbox(
        self,
        *,
        scope: ExecutionScope,
        limit: int = 100,
    ) -> tuple[FiscalInboundDocument, ...]:
        return self._store.list_inbox(scope=scope, limit=limit)

    def manifest(
        self,
        *,
        scope: ExecutionScope,
        access_key: NfeAccessKey,
        event_type: FiscalManifestationType,
        idempotency_key: str,
        actor_id: str,
        occurred_at: datetime,
        protocol_reference: str | None = None,
    ) -> bool:
        return self._store.record_manifestation(
            FiscalManifestation(
                scope=scope,
                access_key=access_key,
                event_type=event_type,
                idempotency_key=idempotency_key,
                actor_id=actor_id,
                correlation_id=scope.correlation_id,
                occurred_at=occurred_at,
                protocol_reference=protocol_reference,
            )
        )
