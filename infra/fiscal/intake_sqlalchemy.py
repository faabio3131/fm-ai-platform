"""Durable, partitioned persistence for preliminary smart fiscal intake."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infra.fiscal.modelos_orm import FiscalArchiveORM, FiscalIntakeCaptureORM
from kordena_fiscal.archive import FiscalArchiveEntry
from kordena_fiscal.domain import Cnpj, ExecutionScope, FiscalEnvironment
from kordena_fiscal.intake import (
    FiscalIntakeArtifact,
    FiscalIntakeAuthority,
    FiscalIntakeCandidateItem,
    FiscalIntakeCapture,
    FiscalIntakeExtraction,
    FiscalIntakeIssueCode,
    FiscalIntakeReconciliation,
    FiscalIntakeReconciliationStatus,
    FiscalIntakeSource,
    FiscalIntakeStatus,
)
from kordena_fiscal.xml import NfeAccessKey

SessionFactory = Callable[[], Session]


class FiscalIntakeStoreError(RuntimeError):
    """Base error for durable intake persistence."""


class FiscalIntakeConflictError(FiscalIntakeStoreError):
    """An intake identity was reused with different immutable input."""


class FiscalIntakeNotFoundError(FiscalIntakeStoreError):
    """The requested capture does not exist in the supplied partition."""


def _db_datetime(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _aware_from_db(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _extraction_payload(extraction: FiscalIntakeExtraction) -> str:
    payload = {
        "access_key": None
        if extraction.access_key is None
        else extraction.access_key.value,
        "issuer_document": None
        if extraction.issuer_document is None
        else extraction.issuer_document.value,
        "recipient_document": None
        if extraction.recipient_document is None
        else extraction.recipient_document.value,
        "confidence": str(extraction.confidence),
        "items": [
            {
                "line_number": item.line_number,
                "product_code": item.product_code,
                "description": item.description,
                "ncm": item.ncm,
                "commercial_unit": item.commercial_unit,
                "quantity": None if item.quantity is None else str(item.quantity),
                "unit_value": None if item.unit_value is None else str(item.unit_value),
                "total_value": None if item.total_value is None else str(item.total_value),
            }
            for item in extraction.items
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _extraction_from_payload(value: str) -> FiscalIntakeExtraction:
    payload = json.loads(value)
    return FiscalIntakeExtraction(
        access_key=None
        if payload["access_key"] is None
        else NfeAccessKey(payload["access_key"]),
        issuer_document=None
        if payload["issuer_document"] is None
        else Cnpj(payload["issuer_document"]),
        recipient_document=None
        if payload["recipient_document"] is None
        else Cnpj(payload["recipient_document"]),
        confidence=Decimal(payload["confidence"]),
        items=tuple(
            FiscalIntakeCandidateItem(
                line_number=item["line_number"],
                product_code=item["product_code"],
                description=item["description"],
                ncm=item["ncm"],
                commercial_unit=item["commercial_unit"],
                quantity=None
                if item["quantity"] is None
                else Decimal(item["quantity"]),
                unit_value=None
                if item["unit_value"] is None
                else Decimal(item["unit_value"]),
                total_value=None
                if item["total_value"] is None
                else Decimal(item["total_value"]),
            )
            for item in payload["items"]
        ),
    )


def _reconciliation_payload(value: FiscalIntakeReconciliation) -> str:
    payload = {
        "status": value.status.value,
        "official_access_key": value.official_access_key.value,
        "issues": [issue.value for issue in value.issues],
        "reconciled_at": value.reconciled_at.isoformat(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _reconciliation_from_payload(value: str) -> FiscalIntakeReconciliation:
    payload = json.loads(value)
    return FiscalIntakeReconciliation(
        status=FiscalIntakeReconciliationStatus(payload["status"]),
        official_access_key=NfeAccessKey(payload["official_access_key"]),
        issues=tuple(FiscalIntakeIssueCode(item) for item in payload["issues"]),
        reconciled_at=datetime.fromisoformat(payload["reconciled_at"]),
    )


class FiscalIntakeStoreSQLAlchemy:
    """Atomic archive and intake state repository."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _query(scope: ExecutionScope, capture_id: str):
        return select(FiscalIntakeCaptureORM).where(
            FiscalIntakeCaptureORM.capture_id == capture_id,
            FiscalIntakeCaptureORM.tenant_id == scope.tenant_id,
            FiscalIntakeCaptureORM.unit_id == scope.unit_id,
            FiscalIntakeCaptureORM.environment == scope.environment.value,
        )

    @staticmethod
    def _to_domain(row: FiscalIntakeCaptureORM) -> FiscalIntakeCapture:
        scope = ExecutionScope(
            tenant_id=row.tenant_id,
            unit_id=row.unit_id,
            environment=FiscalEnvironment(row.environment),
            correlation_id=row.correlation_id,
        )
        return FiscalIntakeCapture(
            capture_id=row.capture_id,
            scope=scope,
            source=FiscalIntakeSource(row.source),
            authority=FiscalIntakeAuthority(row.authority),
            status=FiscalIntakeStatus(row.status),
            idempotency_key=row.idempotency_key,
            archive_entry_id=row.archive_entry_id,
            content_sha256=row.content_sha256,
            media_type=row.media_type,
            captured_at=_aware_from_db(row.captured_at),
            updated_at=_aware_from_db(row.updated_at),
            version=row.version,
            extraction=None
            if row.extraction_json is None
            else _extraction_from_payload(row.extraction_json),
            reconciliation=None
            if row.reconciliation_json is None
            else _reconciliation_from_payload(row.reconciliation_json),
            last_error_code=row.last_error_code,
        )

    def begin(
        self,
        *,
        artifact: FiscalIntakeArtifact,
        archive_entry: FiscalArchiveEntry,
    ) -> tuple[FiscalIntakeCapture, bool]:
        if archive_entry.scope.partition_key != artifact.scope.partition_key:
            raise FiscalIntakeConflictError("archive entry crosses intake partition")
        if (
            archive_entry.document_reference != artifact.capture_id
            or archive_entry.content_sha256 != artifact.content_sha256
        ):
            raise FiscalIntakeConflictError("archive entry differs from intake artifact")
        capture = FiscalIntakeCapture.received(
            artifact,
            archive_entry_id=archive_entry.entry_id,
        )
        try:
            with self._session_factory() as session, session.begin():
                existing = session.execute(
                    self._query(artifact.scope, artifact.capture_id).with_for_update()
                ).scalar_one_or_none()
                if existing is not None:
                    domain = self._to_domain(existing)
                    if (
                        domain.content_sha256 != artifact.content_sha256
                        or domain.media_type != artifact.media_type
                        or domain.source is not artifact.source
                        or domain.archive_entry_id != archive_entry.entry_id
                    ):
                        raise FiscalIntakeConflictError(
                            "idempotency key replay contains different intake content"
                        )
                    return domain, False

                archived = session.get(FiscalArchiveORM, archive_entry.entry_id)
                if archived is not None:
                    if (
                        archived.content_sha256 != archive_entry.content_sha256
                        or archived.document_reference
                        != archive_entry.document_reference
                    ):
                        raise FiscalIntakeConflictError(
                            "archive identity contains different content"
                        )
                else:
                    session.add(
                        FiscalArchiveORM(
                            entry_id=archive_entry.entry_id,
                            tenant_id=archive_entry.scope.tenant_id,
                            unit_id=archive_entry.scope.unit_id,
                            environment=archive_entry.scope.environment.value,
                            correlation_id=archive_entry.scope.correlation_id,
                            document_reference=archive_entry.document_reference,
                            kind=archive_entry.kind.value,
                            content=archive_entry.content,
                            content_sha256=archive_entry.content_sha256,
                            media_type=archive_entry.media_type,
                            archived_at=_db_datetime(archive_entry.archived_at),
                            retention_policy_id=archive_entry.retention.policy_id,
                            retention_policy_version=archive_entry.retention.policy_version,
                            retain_until=archive_entry.retention.retain_until,
                            legal_basis_reference=(
                                archive_entry.retention.legal_basis_reference
                            ),
                            previous_manifest_sha256=(
                                archive_entry.previous_manifest_sha256
                            ),
                        )
                    )
                session.add(
                    FiscalIntakeCaptureORM(
                        capture_id=capture.capture_id,
                        tenant_id=capture.scope.tenant_id,
                        unit_id=capture.scope.unit_id,
                        environment=capture.scope.environment.value,
                        idempotency_key=capture.idempotency_key,
                        source=capture.source.value,
                        authority=capture.authority.value,
                        status=capture.status.value,
                        archive_entry_id=capture.archive_entry_id,
                        content_sha256=capture.content_sha256,
                        media_type=capture.media_type,
                        extraction_json=None,
                        reconciliation_json=None,
                        last_error_code=None,
                        correlation_id=capture.scope.correlation_id,
                        captured_at=_db_datetime(capture.captured_at),
                        updated_at=_db_datetime(capture.updated_at),
                        version=capture.version,
                    )
                )
                session.flush()
                return capture, True
        except IntegrityError as exc:
            raise FiscalIntakeConflictError("intake persistence identity conflict") from exc

    def complete_extraction(
        self,
        *,
        capture: FiscalIntakeCapture,
        extraction: FiscalIntakeExtraction,
        updated_at: datetime,
    ) -> FiscalIntakeCapture:
        with self._session_factory() as session, session.begin():
            row = self._locked(session, capture)
            if row.status in {
                FiscalIntakeStatus.EXTRACTED.value,
                FiscalIntakeStatus.RECONCILED.value,
                FiscalIntakeStatus.DIVERGENT.value,
            }:
                current = self._to_domain(row)
                if current.extraction != extraction:
                    raise FiscalIntakeConflictError(
                        "completed extraction cannot be replaced"
                    )
                return current
            row.status = FiscalIntakeStatus.EXTRACTED.value
            row.extraction_json = _extraction_payload(extraction)
            row.reconciliation_json = None
            row.last_error_code = None
            row.updated_at = _db_datetime(updated_at)
            row.version += 1
            session.flush()
            return self._to_domain(row)

    def mark_extraction_failed(
        self,
        *,
        capture: FiscalIntakeCapture,
        error_code: str,
        updated_at: datetime,
    ) -> FiscalIntakeCapture:
        with self._session_factory() as session, session.begin():
            row = self._locked(session, capture)
            if row.status not in {
                FiscalIntakeStatus.RECEIVED.value,
                FiscalIntakeStatus.EXTRACTION_FAILED.value,
            }:
                return self._to_domain(row)
            row.status = FiscalIntakeStatus.EXTRACTION_FAILED.value
            row.last_error_code = error_code
            row.updated_at = _db_datetime(updated_at)
            row.version += 1
            session.flush()
            return self._to_domain(row)

    def record_reconciliation(
        self,
        *,
        capture: FiscalIntakeCapture,
        reconciliation: FiscalIntakeReconciliation,
    ) -> FiscalIntakeCapture:
        with self._session_factory() as session, session.begin():
            row = self._locked(session, capture)
            current = self._to_domain(row)
            if current.reconciliation is not None:
                if current.reconciliation != reconciliation:
                    raise FiscalIntakeConflictError(
                        "reconciliation cannot be replaced with different evidence"
                    )
                return current
            if current.status is not FiscalIntakeStatus.EXTRACTED:
                raise FiscalIntakeConflictError(
                    "only extracted intake can be reconciled"
                )
            row.status = (
                FiscalIntakeStatus.DIVERGENT.value
                if reconciliation.status is FiscalIntakeReconciliationStatus.DIVERGENT
                else FiscalIntakeStatus.RECONCILED.value
            )
            row.reconciliation_json = _reconciliation_payload(reconciliation)
            row.updated_at = _db_datetime(reconciliation.reconciled_at)
            row.version += 1
            session.flush()
            return self._to_domain(row)

    def _locked(
        self,
        session: Session,
        capture: FiscalIntakeCapture,
    ) -> FiscalIntakeCaptureORM:
        row = session.execute(
            self._query(capture.scope, capture.capture_id).with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise FiscalIntakeNotFoundError("intake capture not found")
        return row

    def get(
        self,
        *,
        scope: ExecutionScope,
        capture_id: str,
    ) -> FiscalIntakeCapture:
        with self._session_factory() as session:
            row = session.execute(self._query(scope, capture_id)).scalar_one_or_none()
            if row is None:
                raise FiscalIntakeNotFoundError("intake capture not found")
            return self._to_domain(row)

    def list(
        self,
        *,
        scope: ExecutionScope,
        limit: int = 100,
    ) -> tuple[FiscalIntakeCapture, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer between 1 and 500")
        with self._session_factory() as session:
            rows = session.execute(
                select(FiscalIntakeCaptureORM)
                .where(
                    FiscalIntakeCaptureORM.tenant_id == scope.tenant_id,
                    FiscalIntakeCaptureORM.unit_id == scope.unit_id,
                    FiscalIntakeCaptureORM.environment == scope.environment.value,
                )
                .order_by(FiscalIntakeCaptureORM.captured_at.desc())
                .limit(limit)
            ).scalars()
            return tuple(self._to_domain(row) for row in rows)
