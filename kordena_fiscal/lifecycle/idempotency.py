"""Deterministic and auditable idempotency semantics for fiscal issuance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import StrEnum
from threading import Lock
from typing import Protocol

from kordena_fiscal.documents import CanonicalFiscalDocument, to_canonical_payload
from kordena_fiscal.domain import FiscalDomainError, FiscalValidationError


class IdempotencyConflictError(FiscalDomainError):
    """Raised when the same issuance intent is reused with unsafe new content."""


class IdempotencyStateError(FiscalDomainError):
    """Raised when an attempt receives an invalid completion transition."""


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Stable opaque key for one host source + fiscal-document issuance intent."""

    value: str

    def __post_init__(self) -> None:
        if len(self.value) != 64:
            raise FiscalValidationError("idempotency key must be a SHA-256 hex digest")
        try:
            int(self.value, 16)
        except ValueError as exc:
            raise FiscalValidationError("idempotency key must be hexadecimal") from exc


class IssuanceAttemptStatus(StrEnum):
    RESERVED = "reserved"
    AUTHORIZED = "authorized"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class IssuanceAttempt:
    """One immutable generation under a stable issuance intent key."""

    key: IdempotencyKey
    generation: int
    request_fingerprint: str
    document_id: str
    status: IssuanceAttemptStatus = IssuanceAttemptStatus.RESERVED
    result_reference: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if self.generation < 1:
            raise FiscalValidationError("idempotency generation must be >= 1")
        if len(self.request_fingerprint) != 64:
            raise FiscalValidationError("request_fingerprint must be SHA-256")
        document_id = self.document_id.strip()
        if not document_id:
            raise FiscalValidationError("document_id must not be blank")
        object.__setattr__(self, "document_id", document_id)
        if not isinstance(self.status, IssuanceAttemptStatus):
            raise FiscalValidationError("status must be IssuanceAttemptStatus")
        if self.status is IssuanceAttemptStatus.RESERVED:
            if self.result_reference is not None or self.rejection_reason is not None:
                raise FiscalValidationError(
                    "reserved attempt cannot have result or rejection metadata"
                )
        if self.status is IssuanceAttemptStatus.AUTHORIZED:
            if not self.result_reference or self.rejection_reason is not None:
                raise FiscalValidationError(
                    "authorized attempt requires result_reference only"
                )
        if self.status is IssuanceAttemptStatus.REJECTED:
            if not self.rejection_reason or self.result_reference is not None:
                raise FiscalValidationError(
                    "rejected attempt requires rejection_reason only"
                )


@dataclass(frozen=True, slots=True)
class IdempotencyReservation:
    attempt: IssuanceAttempt
    replay: bool


class IdempotencyStore(Protocol):
    """Atomic persistence contract required by production adapters."""

    def reserve(
        self,
        key: IdempotencyKey,
        request_fingerprint: str,
        document_id: str,
    ) -> IdempotencyReservation: ...

    def mark_authorized(
        self,
        key: IdempotencyKey,
        generation: int,
        result_reference: str,
    ) -> IssuanceAttempt: ...

    def mark_rejected(
        self,
        key: IdempotencyKey,
        generation: int,
        rejection_reason: str,
    ) -> IssuanceAttempt: ...

    def attempts(self, key: IdempotencyKey) -> tuple[IssuanceAttempt, ...]: ...


def build_issuance_key(document: CanonicalFiscalDocument) -> IdempotencyKey:
    """Build stable key excluding transient correlation/document identifiers."""

    material = {
        "tenant_id": document.scope.tenant_id,
        "unit_id": document.scope.unit_id,
        "environment": document.scope.environment.value,
        "source_type": document.source.source_type,
        "source_id": document.source.source_id,
        "document_kind": document.document_kind.value,
        "operation": "issue",
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    return IdempotencyKey(hashlib.sha256(encoded).hexdigest())


def build_request_fingerprint(document: CanonicalFiscalDocument) -> str:
    """Fingerprint semantic request content while ignoring retry metadata."""

    payload = to_canonical_payload(document)
    payload.pop("document_id", None)
    scope = payload.get("scope")
    if isinstance(scope, dict):
        scope.pop("correlation_id", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class InMemoryIdempotencyStore:
    """Thread-safe reference store for tests; not a distributed production store."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, list[IssuanceAttempt]] = {}

    def reserve(
        self,
        key: IdempotencyKey,
        request_fingerprint: str,
        document_id: str,
    ) -> IdempotencyReservation:
        with self._lock:
            history = self._records.setdefault(key.value, [])
            if not history:
                attempt = IssuanceAttempt(
                    key=key,
                    generation=1,
                    request_fingerprint=request_fingerprint,
                    document_id=document_id,
                )
                history.append(attempt)
                return IdempotencyReservation(attempt=attempt, replay=False)

            latest = history[-1]
            if latest.request_fingerprint == request_fingerprint:
                return IdempotencyReservation(attempt=latest, replay=True)

            if latest.status is not IssuanceAttemptStatus.REJECTED:
                raise IdempotencyConflictError(
                    "issuance intent already exists with different content "
                    "and is not safely rejected"
                )

            attempt = IssuanceAttempt(
                key=key,
                generation=latest.generation + 1,
                request_fingerprint=request_fingerprint,
                document_id=document_id,
            )
            history.append(attempt)
            return IdempotencyReservation(attempt=attempt, replay=False)

    def mark_authorized(
        self,
        key: IdempotencyKey,
        generation: int,
        result_reference: str,
    ) -> IssuanceAttempt:
        reference = result_reference.strip()
        if not reference:
            raise FiscalValidationError("result_reference must not be blank")
        with self._lock:
            latest = self._latest_for_update(key, generation)
            if latest.status is IssuanceAttemptStatus.AUTHORIZED:
                if latest.result_reference != reference:
                    raise IdempotencyStateError(
                        "authorized attempt cannot change result_reference"
                    )
                return latest
            if latest.status is not IssuanceAttemptStatus.RESERVED:
                raise IdempotencyStateError("only reserved attempt can become authorized")
            updated = replace(
                latest,
                status=IssuanceAttemptStatus.AUTHORIZED,
                result_reference=reference,
            )
            self._records[key.value][-1] = updated
            return updated

    def mark_rejected(
        self,
        key: IdempotencyKey,
        generation: int,
        rejection_reason: str,
    ) -> IssuanceAttempt:
        reason = rejection_reason.strip()
        if not reason:
            raise FiscalValidationError("rejection_reason must not be blank")
        with self._lock:
            latest = self._latest_for_update(key, generation)
            if latest.status is IssuanceAttemptStatus.REJECTED:
                if latest.rejection_reason != reason:
                    raise IdempotencyStateError(
                        "rejected attempt cannot change rejection_reason"
                    )
                return latest
            if latest.status is not IssuanceAttemptStatus.RESERVED:
                raise IdempotencyStateError("only reserved attempt can become rejected")
            updated = replace(
                latest,
                status=IssuanceAttemptStatus.REJECTED,
                rejection_reason=reason,
            )
            self._records[key.value][-1] = updated
            return updated

    def attempts(self, key: IdempotencyKey) -> tuple[IssuanceAttempt, ...]:
        with self._lock:
            return tuple(self._records.get(key.value, ()))

    def _latest_for_update(
        self,
        key: IdempotencyKey,
        generation: int,
    ) -> IssuanceAttempt:
        history = self._records.get(key.value)
        if not history:
            raise IdempotencyStateError("idempotency key has no reserved attempt")
        latest = history[-1]
        if latest.generation != generation:
            raise IdempotencyStateError("only the latest generation can be updated")
        return latest


class IdempotencyCoordinator:
    """High-level issuance idempotency API used by application orchestration."""

    def __init__(self, store: IdempotencyStore) -> None:
        self._store = store

    def begin(self, document: CanonicalFiscalDocument) -> IdempotencyReservation:
        if not isinstance(document, CanonicalFiscalDocument):
            raise FiscalValidationError("document must be CanonicalFiscalDocument")
        return self._store.reserve(
            build_issuance_key(document),
            build_request_fingerprint(document),
            document.document_id,
        )

    def mark_authorized(
        self,
        key: IdempotencyKey,
        generation: int,
        result_reference: str,
    ) -> IssuanceAttempt:
        return self._store.mark_authorized(key, generation, result_reference)

    def mark_rejected(
        self,
        key: IdempotencyKey,
        generation: int,
        rejection_reason: str,
    ) -> IssuanceAttempt:
        return self._store.mark_rejected(key, generation, rejection_reason)
