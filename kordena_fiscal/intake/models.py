"""Smart Fiscal Intake value objects with explicit authority boundaries."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from kordena_fiscal.domain import Cnpj, ExecutionScope, FiscalValidationError
from kordena_fiscal.inbound import FiscalInboundDocument
from kordena_fiscal.xml import NfeAccessKey

_MAX_ARTIFACT_BYTES = 10 * 1024 * 1024


def _required_text(value: str, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise FiscalValidationError(f"{field} must be text")
    normalized = value.strip()
    if not normalized:
        raise FiscalValidationError(f"{field} must not be blank")
    if len(normalized) > maximum:
        raise FiscalValidationError(f"{field} exceeds max length {maximum}")
    return normalized


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise FiscalValidationError(f"{field} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise FiscalValidationError(f"{field} must be timezone-aware")
    return value


def _optional_decimal(value: Decimal | None, field: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise FiscalValidationError(f"{field} must be a non-negative finite Decimal")
    return value


class FiscalIntakeSource(StrEnum):
    DFE = "dfe"
    XML = "xml"
    PDF = "pdf"
    IMAGE = "image"
    CAMERA = "camera"


class FiscalIntakeAuthority(StrEnum):
    OFFICIAL = "official"
    PRELIMINARY = "preliminary"


class FiscalIntakeStatus(StrEnum):
    RECEIVED = "received"
    EXTRACTION_FAILED = "extraction_failed"
    EXTRACTED = "extracted"
    RECONCILED = "reconciled"
    DIVERGENT = "divergent"


class FiscalIntakeReconciliationStatus(StrEnum):
    MATCHED = "matched"
    PARTIAL = "partial"
    DIVERGENT = "divergent"


class FiscalIntakeIssueCode(StrEnum):
    ACCESS_KEY_MISMATCH = "access_key_mismatch"
    ISSUER_MISMATCH = "issuer_mismatch"
    RECIPIENT_MISMATCH = "recipient_mismatch"
    ITEM_COUNT_MISMATCH = "item_count_mismatch"
    PRODUCT_CODE_MISMATCH = "product_code_mismatch"
    DESCRIPTION_MISMATCH = "description_mismatch"
    NCM_MISMATCH = "ncm_mismatch"
    COMMERCIAL_UNIT_MISMATCH = "commercial_unit_mismatch"
    QUANTITY_MISMATCH = "quantity_mismatch"
    UNIT_VALUE_MISMATCH = "unit_value_mismatch"
    TOTAL_VALUE_MISMATCH = "total_value_mismatch"
    PRELIMINARY_FIELD_MISSING = "preliminary_field_missing"


@dataclass(frozen=True, slots=True)
class FiscalIntakeArtifact:
    scope: ExecutionScope
    source: FiscalIntakeSource
    media_type: str
    content: bytes
    idempotency_key: str
    captured_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if self.source not in {
            FiscalIntakeSource.PDF,
            FiscalIntakeSource.IMAGE,
            FiscalIntakeSource.CAMERA,
        }:
            raise FiscalValidationError("preliminary artifact source is unsupported")
        media_type = _required_text(self.media_type, "media_type", 128).casefold()
        allowed = {
            FiscalIntakeSource.PDF: {"application/pdf"},
            FiscalIntakeSource.IMAGE: {"image/jpeg", "image/png"},
            FiscalIntakeSource.CAMERA: {"image/jpeg", "image/png"},
        }[self.source]
        if media_type not in allowed:
            raise FiscalValidationError("media_type is incompatible with intake source")
        object.__setattr__(self, "media_type", media_type)
        if not isinstance(self.content, bytes) or not self.content:
            raise FiscalValidationError("content must be non-empty bytes")
        if len(self.content) > _MAX_ARTIFACT_BYTES:
            raise FiscalValidationError("content exceeds 10 MiB")
        object.__setattr__(
            self,
            "idempotency_key",
            _required_text(self.idempotency_key, "idempotency_key", 160),
        )
        _aware(self.captured_at, "captured_at")

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def capture_id(self) -> str:
        material = (
            f"{self.scope.tenant_id}|{self.scope.unit_id}|"
            f"{self.scope.environment.value}|{self.idempotency_key}"
        ).encode()
        return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class FiscalIntakeCandidateItem:
    line_number: int
    description: str
    product_code: str | None = None
    ncm: str | None = None
    commercial_unit: str | None = None
    quantity: Decimal | None = None
    unit_value: Decimal | None = None
    total_value: Decimal | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.line_number, int)
            or isinstance(self.line_number, bool)
            or self.line_number < 1
        ):
            raise FiscalValidationError("line_number must be a positive integer")
        object.__setattr__(
            self,
            "description",
            _required_text(self.description, "description", 512),
        )
        if self.product_code is not None:
            object.__setattr__(
                self,
                "product_code",
                _required_text(self.product_code, "product_code", 128),
            )
        if self.ncm is not None:
            ncm = _required_text(self.ncm, "ncm", 8)
            if len(ncm) != 8 or not ncm.isdigit():
                raise FiscalValidationError("ncm must contain exactly 8 digits")
            object.__setattr__(self, "ncm", ncm)
        if self.commercial_unit is not None:
            object.__setattr__(
                self,
                "commercial_unit",
                _required_text(self.commercial_unit, "commercial_unit", 16).upper(),
            )
        for field in ("quantity", "unit_value", "total_value"):
            object.__setattr__(self, field, _optional_decimal(getattr(self, field), field))
        if self.quantity == 0:
            raise FiscalValidationError("quantity must be greater than zero")


@dataclass(frozen=True, slots=True)
class FiscalIntakeExtraction:
    items: tuple[FiscalIntakeCandidateItem, ...]
    confidence: Decimal
    access_key: NfeAccessKey | None = None
    issuer_document: Cnpj | None = None
    recipient_document: Cnpj | None = None

    def __post_init__(self) -> None:
        if not self.items or len(self.items) > 500:
            raise FiscalValidationError("extraction must contain between 1 and 500 items")
        lines = tuple(item.line_number for item in self.items)
        if len(lines) != len(set(lines)):
            raise FiscalValidationError("extraction line_number must be unique")
        if lines != tuple(sorted(lines)):
            raise FiscalValidationError("extraction items must be ordered by line_number")
        if (
            not isinstance(self.confidence, Decimal)
            or not self.confidence.is_finite()
            or not Decimal(0) <= self.confidence <= Decimal(1)
        ):
            raise FiscalValidationError("confidence must be a Decimal between 0 and 1")
        if self.access_key is not None and not isinstance(self.access_key, NfeAccessKey):
            raise FiscalValidationError("access_key must be NfeAccessKey")
        if self.issuer_document is not None and not isinstance(
            self.issuer_document, Cnpj
        ):
            raise FiscalValidationError("issuer_document must be Cnpj")
        if self.recipient_document is not None and not isinstance(
            self.recipient_document, Cnpj
        ):
            raise FiscalValidationError("recipient_document must be Cnpj")


@dataclass(frozen=True, slots=True)
class FiscalIntakeReconciliation:
    status: FiscalIntakeReconciliationStatus
    official_access_key: NfeAccessKey
    issues: tuple[FiscalIntakeIssueCode, ...]
    reconciled_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.status, FiscalIntakeReconciliationStatus):
            raise FiscalValidationError("status must be reconciliation status")
        if not isinstance(self.official_access_key, NfeAccessKey):
            raise FiscalValidationError("official_access_key must be NfeAccessKey")
        if len(self.issues) != len(set(self.issues)):
            raise FiscalValidationError("reconciliation issues must be unique")
        if self.status is FiscalIntakeReconciliationStatus.MATCHED and self.issues:
            raise FiscalValidationError("matched reconciliation cannot contain issues")
        if self.status is not FiscalIntakeReconciliationStatus.MATCHED and not self.issues:
            raise FiscalValidationError("non-matched reconciliation requires issues")
        _aware(self.reconciled_at, "reconciled_at")


@dataclass(frozen=True, slots=True)
class FiscalIntakeCapture:
    capture_id: str
    scope: ExecutionScope
    source: FiscalIntakeSource
    authority: FiscalIntakeAuthority
    status: FiscalIntakeStatus
    idempotency_key: str
    archive_entry_id: str
    content_sha256: str
    media_type: str
    captured_at: datetime
    updated_at: datetime
    version: int = 1
    extraction: FiscalIntakeExtraction | None = None
    reconciliation: FiscalIntakeReconciliation | None = None
    last_error_code: str | None = None

    def __post_init__(self) -> None:
        for field in ("capture_id", "archive_entry_id", "content_sha256"):
            value = _required_text(getattr(self, field), field, 64).lower()
            if len(value) != 64:
                raise FiscalValidationError(f"{field} must be SHA-256 hex")
            try:
                int(value, 16)
            except ValueError as exc:
                raise FiscalValidationError(f"{field} must be hexadecimal") from exc
            object.__setattr__(self, field, value)
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.source, FiscalIntakeSource):
            raise FiscalValidationError("source must be FiscalIntakeSource")
        if self.authority is not FiscalIntakeAuthority.PRELIMINARY:
            raise FiscalValidationError("durable capture authority must be preliminary")
        if not isinstance(self.status, FiscalIntakeStatus):
            raise FiscalValidationError("status must be FiscalIntakeStatus")
        object.__setattr__(
            self,
            "idempotency_key",
            _required_text(self.idempotency_key, "idempotency_key", 160),
        )
        object.__setattr__(
            self,
            "media_type",
            _required_text(self.media_type, "media_type", 128).casefold(),
        )
        _aware(self.captured_at, "captured_at")
        _aware(self.updated_at, "updated_at")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise FiscalValidationError("version must be a positive integer")
        if self.status in {
            FiscalIntakeStatus.EXTRACTED,
            FiscalIntakeStatus.RECONCILED,
            FiscalIntakeStatus.DIVERGENT,
        } and self.extraction is None:
            raise FiscalValidationError("capture status requires extraction")
        if self.status is FiscalIntakeStatus.EXTRACTION_FAILED and self.last_error_code is None:
            raise FiscalValidationError("failed capture requires last_error_code")
        if self.last_error_code is not None:
            object.__setattr__(
                self,
                "last_error_code",
                _required_text(self.last_error_code, "last_error_code", 128),
            )
        if self.reconciliation is not None and self.status not in {
            FiscalIntakeStatus.RECONCILED,
            FiscalIntakeStatus.DIVERGENT,
        }:
            raise FiscalValidationError("reconciliation requires a terminal intake status")
        if self.status in {
            FiscalIntakeStatus.RECONCILED,
            FiscalIntakeStatus.DIVERGENT,
        } and self.reconciliation is None:
            raise FiscalValidationError("terminal intake status requires reconciliation")
        if (
            self.status is FiscalIntakeStatus.DIVERGENT
            and self.reconciliation is not None
            and self.reconciliation.status
            is not FiscalIntakeReconciliationStatus.DIVERGENT
        ):
            raise FiscalValidationError("divergent intake requires divergent reconciliation")
        if (
            self.status is FiscalIntakeStatus.RECONCILED
            and self.reconciliation is not None
            and self.reconciliation.status
            is FiscalIntakeReconciliationStatus.DIVERGENT
        ):
            raise FiscalValidationError("reconciled intake cannot be divergent")

    @classmethod
    def received(
        cls,
        artifact: FiscalIntakeArtifact,
        *,
        archive_entry_id: str,
    ) -> FiscalIntakeCapture:
        return cls(
            capture_id=artifact.capture_id,
            scope=artifact.scope,
            source=artifact.source,
            authority=FiscalIntakeAuthority.PRELIMINARY,
            status=FiscalIntakeStatus.RECEIVED,
            idempotency_key=artifact.idempotency_key,
            archive_entry_id=archive_entry_id,
            content_sha256=artifact.content_sha256,
            media_type=artifact.media_type,
            captured_at=artifact.captured_at,
            updated_at=artifact.captured_at,
        )

    def with_extraction(
        self,
        extraction: FiscalIntakeExtraction,
        *,
        updated_at: datetime,
    ) -> FiscalIntakeCapture:
        return replace(
            self,
            status=FiscalIntakeStatus.EXTRACTED,
            extraction=extraction,
            reconciliation=None,
            last_error_code=None,
            updated_at=_aware(updated_at, "updated_at"),
            version=self.version + 1,
        )


@dataclass(frozen=True, slots=True)
class FiscalIntakeOfficialResult:
    source: FiscalIntakeSource
    authority: FiscalIntakeAuthority
    document: FiscalInboundDocument

    def __post_init__(self) -> None:
        if self.source not in {FiscalIntakeSource.DFE, FiscalIntakeSource.XML}:
            raise FiscalValidationError("official result source must be DF-e or XML")
        if self.authority is not FiscalIntakeAuthority.OFFICIAL:
            raise FiscalValidationError("official result must have official authority")
        if not isinstance(self.document, FiscalInboundDocument):
            raise FiscalValidationError("document must be FiscalInboundDocument")
