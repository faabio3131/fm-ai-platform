"""Provider-neutral inbound fiscal value objects."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from kordena_fiscal.domain import Cnpj, ExecutionScope, FiscalValidationError
from kordena_fiscal.xml import NfeAccessKey


def _required_text(value: str, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise FiscalValidationError(f"{field} must be text")
    normalized = value.strip()
    if not normalized:
        raise FiscalValidationError(f"{field} must not be blank")
    if len(normalized) > max_length:
        raise FiscalValidationError(f"{field} exceeds max length {max_length}")
    return normalized


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise FiscalValidationError(f"{field} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise FiscalValidationError(f"{field} must be timezone-aware")
    return value


def normalize_nsu(value: str, field: str = "nsu") -> str:
    normalized = _required_text(value, field, 15)
    if not normalized.isdigit():
        raise FiscalValidationError(f"{field} must contain only digits")
    return normalized.zfill(15)


class FiscalInboundSource(StrEnum):
    DFE = "dfe"
    XML_UPLOAD = "xml_upload"


class FiscalInboundStatus(StrEnum):
    DETECTED = "detected"
    MANIFESTED = "manifested"


class FiscalManifestationType(StrEnum):
    ACKNOWLEDGEMENT = "acknowledgement"
    CONFIRMATION = "confirmation"
    UNKNOWN_OPERATION = "unknown_operation"
    OPERATION_NOT_PERFORMED = "operation_not_performed"


@dataclass(frozen=True, slots=True)
class FiscalInboundItem:
    line_number: int
    product_code: str
    description: str
    ncm: str
    commercial_unit: str
    quantity: Decimal
    unit_value: Decimal
    total_value: Decimal

    def __post_init__(self) -> None:
        if (
            not isinstance(self.line_number, int)
            or isinstance(self.line_number, bool)
            or self.line_number < 1
        ):
            raise FiscalValidationError("line_number must be a positive integer")
        object.__setattr__(
            self, "product_code", _required_text(self.product_code, "product_code", 128)
        )
        object.__setattr__(
            self, "description", _required_text(self.description, "description", 512)
        )
        ncm = _required_text(self.ncm, "ncm", 8)
        if len(ncm) != 8 or not ncm.isdigit():
            raise FiscalValidationError("ncm must contain exactly 8 digits")
        object.__setattr__(self, "ncm", ncm)
        object.__setattr__(
            self,
            "commercial_unit",
            _required_text(self.commercial_unit, "commercial_unit", 16).upper(),
        )
        for field in ("quantity", "unit_value", "total_value"):
            value = getattr(self, field)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise FiscalValidationError(f"{field} must be a finite Decimal")
            if value < 0 or (field == "quantity" and value == 0):
                raise FiscalValidationError(f"{field} is outside the accepted range")


@dataclass(frozen=True, slots=True)
class FiscalInboundDocument:
    scope: ExecutionScope
    access_key: NfeAccessKey
    recipient_document: Cnpj
    issuer_document: Cnpj
    issuer_name: str
    issued_at: datetime
    status: FiscalInboundStatus
    source: FiscalInboundSource
    xml_content: bytes
    items: tuple[FiscalInboundItem, ...]
    discovered_at: datetime
    nsu: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.access_key, NfeAccessKey):
            raise FiscalValidationError("access_key must be NfeAccessKey")
        if not isinstance(self.recipient_document, Cnpj):
            raise FiscalValidationError("recipient_document must be Cnpj")
        if not isinstance(self.issuer_document, Cnpj):
            raise FiscalValidationError("issuer_document must be Cnpj")
        if self.access_key.issuer_identifier != self.issuer_document.value:
            raise FiscalValidationError("access key issuer differs from XML issuer")
        object.__setattr__(
            self, "issuer_name", _required_text(self.issuer_name, "issuer_name", 256)
        )
        _aware(self.issued_at, "issued_at")
        _aware(self.discovered_at, "discovered_at")
        if not isinstance(self.status, FiscalInboundStatus):
            raise FiscalValidationError("status must be FiscalInboundStatus")
        if not isinstance(self.source, FiscalInboundSource):
            raise FiscalValidationError("source must be FiscalInboundSource")
        if not isinstance(self.xml_content, bytes) or not self.xml_content:
            raise FiscalValidationError("xml_content must be non-empty bytes")
        if not self.items:
            raise FiscalValidationError("inbound document must contain items")
        line_numbers = tuple(item.line_number for item in self.items)
        if len(line_numbers) != len(set(line_numbers)):
            raise FiscalValidationError("inbound item line_number must be unique")
        if self.nsu is not None:
            object.__setattr__(self, "nsu", normalize_nsu(self.nsu))
        if self.source is FiscalInboundSource.DFE and self.nsu is None:
            raise FiscalValidationError("DF-e inbound document requires nsu")
        if self.source is FiscalInboundSource.XML_UPLOAD and self.nsu is not None:
            raise FiscalValidationError("XML upload must not declare nsu")

    @property
    def xml_sha256(self) -> str:
        return hashlib.sha256(self.xml_content).hexdigest()

    @property
    def inbound_id(self) -> str:
        material = (
            f"{self.scope.tenant_id}|{self.scope.unit_id}|"
            f"{self.scope.environment.value}|{self.access_key.value}"
        ).encode()
        return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class FiscalNsuCheckpoint:
    scope: ExecutionScope
    recipient_document: Cnpj
    last_nsu: str
    max_nsu: str
    version: int
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.recipient_document, Cnpj):
            raise FiscalValidationError("recipient_document must be Cnpj")
        object.__setattr__(self, "last_nsu", normalize_nsu(self.last_nsu, "last_nsu"))
        object.__setattr__(self, "max_nsu", normalize_nsu(self.max_nsu, "max_nsu"))
        if int(self.max_nsu) < int(self.last_nsu):
            raise FiscalValidationError("max_nsu must not precede last_nsu")
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise FiscalValidationError("version must be a positive integer")
        _aware(self.updated_at, "updated_at")


@dataclass(frozen=True, slots=True)
class FiscalManifestation:
    scope: ExecutionScope
    access_key: NfeAccessKey
    event_type: FiscalManifestationType
    idempotency_key: str
    actor_id: str
    correlation_id: str
    occurred_at: datetime
    protocol_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.access_key, NfeAccessKey):
            raise FiscalValidationError("access_key must be NfeAccessKey")
        if not isinstance(self.event_type, FiscalManifestationType):
            raise FiscalValidationError("event_type must be FiscalManifestationType")
        object.__setattr__(
            self,
            "idempotency_key",
            _required_text(self.idempotency_key, "idempotency_key", 160),
        )
        object.__setattr__(self, "actor_id", _required_text(self.actor_id, "actor_id", 128))
        object.__setattr__(
            self,
            "correlation_id",
            _required_text(self.correlation_id, "correlation_id", 256),
        )
        _aware(self.occurred_at, "occurred_at")
        if self.protocol_reference is not None:
            object.__setattr__(
                self,
                "protocol_reference",
                _required_text(self.protocol_reference, "protocol_reference", 512),
            )

    @property
    def manifestation_id(self) -> str:
        material = (
            f"{self.scope.tenant_id}|{self.scope.unit_id}|"
            f"{self.scope.environment.value}|{self.idempotency_key}"
        ).encode()
        return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class DfeDistributionEntry:
    nsu: str
    xml_content: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "nsu", normalize_nsu(self.nsu))
        if not isinstance(self.xml_content, bytes) or not self.xml_content:
            raise FiscalValidationError("xml_content must be non-empty bytes")


@dataclass(frozen=True, slots=True)
class DfeDistributionBatch:
    entries: tuple[DfeDistributionEntry, ...]
    last_nsu: str
    max_nsu: str
    fetched_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "last_nsu", normalize_nsu(self.last_nsu, "last_nsu"))
        object.__setattr__(self, "max_nsu", normalize_nsu(self.max_nsu, "max_nsu"))
        _aware(self.fetched_at, "fetched_at")
        if int(self.max_nsu) < int(self.last_nsu):
            raise FiscalValidationError("max_nsu must not precede last_nsu")
        values = tuple(int(entry.nsu) for entry in self.entries)
        if values != tuple(sorted(values)) or len(values) != len(set(values)):
            raise FiscalValidationError("DF-e entries must have unique ascending NSUs")
        if values and values[-1] > int(self.last_nsu):
            raise FiscalValidationError("batch last_nsu must cover every entry")
