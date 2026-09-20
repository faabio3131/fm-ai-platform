"""Application boundary for the authority-aware smart fiscal intake."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from application.fiscal_inbound import FiscalInboundApplication
from kordena_fiscal.archive import (
    FiscalArchiveEntry,
    FiscalArchiveKind,
    RetentionPolicyMetadata,
)
from kordena_fiscal.domain import Cnpj, ExecutionScope, FiscalValidationError
from kordena_fiscal.inbound import FiscalInboundDocument, FiscalInboundSource
from kordena_fiscal.intake import (
    FiscalIntakeArtifact,
    FiscalIntakeAuthority,
    FiscalIntakeCapture,
    FiscalIntakeExtraction,
    FiscalIntakeOfficialResult,
    FiscalIntakeReconciliation,
    FiscalIntakeSource,
    FiscalIntakeStatus,
    reconcile_fiscal_intake,
)


class FiscalIntakeExtractionError(RuntimeError):
    """A preliminary artifact was archived but could not be extracted safely."""


class FiscalIntakeExtractor(Protocol):
    def extract(self, artifact: FiscalIntakeArtifact) -> FiscalIntakeExtraction: ...


class FiscalIntakeStore(Protocol):
    def begin(
        self,
        *,
        artifact: FiscalIntakeArtifact,
        archive_entry: FiscalArchiveEntry,
    ) -> tuple[FiscalIntakeCapture, bool]: ...

    def complete_extraction(
        self,
        *,
        capture: FiscalIntakeCapture,
        extraction: FiscalIntakeExtraction,
        updated_at: datetime,
    ) -> FiscalIntakeCapture: ...

    def mark_extraction_failed(
        self,
        *,
        capture: FiscalIntakeCapture,
        error_code: str,
        updated_at: datetime,
    ) -> FiscalIntakeCapture: ...

    def record_reconciliation(
        self,
        *,
        capture: FiscalIntakeCapture,
        reconciliation: FiscalIntakeReconciliation,
    ) -> FiscalIntakeCapture: ...

    def get(self, *, scope: ExecutionScope, capture_id: str) -> FiscalIntakeCapture: ...


class FiscalOfficialDocumentStore(Protocol):
    def get(
        self,
        *,
        scope: ExecutionScope,
        access_key: str,
    ) -> FiscalInboundDocument: ...


class SmartFiscalIntakeApplication:
    """Converges fiscal sources without granting AI official authority."""

    def __init__(
        self,
        *,
        store: FiscalIntakeStore,
        inbound_application: FiscalInboundApplication,
        inbound_store: FiscalOfficialDocumentStore,
    ) -> None:
        self._store = store
        self._inbound_application = inbound_application
        self._inbound_store = inbound_store

    def ingest_preliminary(
        self,
        *,
        scope: ExecutionScope,
        source: FiscalIntakeSource,
        media_type: str,
        content: bytes,
        idempotency_key: str,
        captured_at: datetime,
        retention: RetentionPolicyMetadata,
        extractor: FiscalIntakeExtractor,
    ) -> tuple[FiscalIntakeCapture, bool]:
        artifact = FiscalIntakeArtifact(
            scope=scope,
            source=source,
            media_type=media_type,
            content=content,
            idempotency_key=idempotency_key,
            captured_at=captured_at,
        )
        archive_entry = FiscalArchiveEntry.build(
            scope=scope,
            document_reference=artifact.capture_id,
            kind=FiscalArchiveKind.OTHER,
            content=content,
            media_type=artifact.media_type,
            archived_at=captured_at,
            retention=retention,
        )
        capture, created = self._store.begin(
            artifact=artifact,
            archive_entry=archive_entry,
        )
        if capture.status in {
            FiscalIntakeStatus.EXTRACTED,
            FiscalIntakeStatus.RECONCILED,
            FiscalIntakeStatus.DIVERGENT,
        }:
            return capture, False

        try:
            extraction = extractor.extract(artifact)
            if not isinstance(extraction, FiscalIntakeExtraction):
                raise FiscalValidationError(
                    "extractor must return FiscalIntakeExtraction"
                )
        except FiscalValidationError as exc:
            self._store.mark_extraction_failed(
                capture=capture,
                error_code="intake.invalid_extraction",
                updated_at=captured_at,
            )
            raise FiscalIntakeExtractionError(
                "preliminary extraction failed validation"
            ) from exc
        except Exception as exc:
            self._store.mark_extraction_failed(
                capture=capture,
                error_code="intake.extractor_unavailable",
                updated_at=captured_at,
            )
            raise FiscalIntakeExtractionError(
                "preliminary extraction provider failed"
            ) from exc

        completed = self._store.complete_extraction(
            capture=capture,
            extraction=extraction,
            updated_at=captured_at,
        )
        return completed, created

    def ingest_official_xml(
        self,
        *,
        scope: ExecutionScope,
        recipient_document: Cnpj,
        xml_content: bytes,
        received_at: datetime,
    ) -> tuple[FiscalIntakeOfficialResult, bool]:
        document, created = self._inbound_application.ingest_xml_upload(
            scope=scope,
            recipient_document=recipient_document,
            xml_content=xml_content,
            received_at=received_at,
        )
        return self.normalize_official(document), created

    @staticmethod
    def normalize_official(
        document: FiscalInboundDocument,
    ) -> FiscalIntakeOfficialResult:
        source = (
            FiscalIntakeSource.DFE
            if document.source is FiscalInboundSource.DFE
            else FiscalIntakeSource.XML
        )
        return FiscalIntakeOfficialResult(
            source=source,
            authority=FiscalIntakeAuthority.OFFICIAL,
            document=document,
        )

    def reconcile(
        self,
        *,
        scope: ExecutionScope,
        capture_id: str,
        official_access_key: str,
        reconciled_at: datetime,
    ) -> FiscalIntakeCapture:
        capture = self._store.get(scope=scope, capture_id=capture_id)
        if capture.reconciliation is not None:
            if capture.reconciliation.official_access_key.value != official_access_key:
                raise FiscalValidationError(
                    "capture is already reconciled to another official document"
                )
            return capture
        document = self._inbound_store.get(
            scope=scope,
            access_key=official_access_key,
        )
        reconciliation = reconcile_fiscal_intake(
            capture,
            document,
            reconciled_at=reconciled_at,
        )
        return self._store.record_reconciliation(
            capture=capture,
            reconciliation=reconciliation,
        )
