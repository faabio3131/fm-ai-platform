"""Deterministic fiscal outbox, lease and retry semantics."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from threading import Lock
from typing import Protocol

from kordena_fiscal.domain import ExecutionScope, FiscalDomainError, FiscalValidationError


class FiscalOutboxError(FiscalDomainError):
    """Base error for fiscal outbox invariants."""


class OutboxConflictError(FiscalOutboxError):
    """Raised when a stable deduplication key is reused with different content."""


class OutboxStateError(FiscalOutboxError):
    """Raised when an outbox transition violates the expected state/version."""


class FiscalOutboxStatus(StrEnum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"


class FiscalDispatchStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILURE = "retryable_failure"
    FATAL_FAILURE = "fatal_failure"


def _required(value: str, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise FiscalValidationError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise FiscalValidationError(f"{field_name} exceeds max length {max_length}")
    return normalized


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FiscalValidationError(f"{field_name} must be timezone-aware")
    return value


def _sha256_hex(value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise FiscalValidationError(f"{field_name} must be SHA-256 hex")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise FiscalValidationError(f"{field_name} must be hexadecimal") from exc
    return normalized


@dataclass(frozen=True, slots=True)
class FiscalRetryPolicy:
    max_attempts: int = 5
    initial_delay_seconds: int = 5
    multiplier: int = 2
    max_delay_seconds: int = 300

    def __post_init__(self) -> None:
        for field_name in (
            "max_attempts",
            "initial_delay_seconds",
            "multiplier",
            "max_delay_seconds",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise FiscalValidationError(f"{field_name} must be an integer")
            if value < 1:
                raise FiscalValidationError(f"{field_name} must be >= 1")
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise FiscalValidationError(
                "max_delay_seconds must be >= initial_delay_seconds"
            )

    def delay_for_attempt(self, attempt_number: int) -> timedelta:
        if not isinstance(attempt_number, int) or isinstance(attempt_number, bool):
            raise FiscalValidationError("attempt_number must be an integer")
        if attempt_number < 1:
            raise FiscalValidationError("attempt_number must be >= 1")
        seconds = self.initial_delay_seconds * self.multiplier ** (attempt_number - 1)
        return timedelta(seconds=min(seconds, self.max_delay_seconds))


@dataclass(frozen=True, slots=True)
class FiscalOutboxEntry:
    entry_id: str
    scope: ExecutionScope
    operation: str
    deduplication_key: str
    payload: bytes
    payload_sha256: str
    created_at: datetime
    available_at: datetime
    status: FiscalOutboxStatus = FiscalOutboxStatus.PENDING
    attempt_count: int = 0
    lease_until: datetime | None = None
    last_error: str | None = None
    completion_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", _sha256_hex(self.entry_id, "entry_id"))
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        operation = _required(self.operation, "operation", 128).lower()
        object.__setattr__(self, "operation", operation)
        object.__setattr__(
            self,
            "deduplication_key",
            _required(self.deduplication_key, "deduplication_key", 512),
        )
        if not isinstance(self.payload, bytes) or not self.payload:
            raise FiscalValidationError("payload must be non-empty bytes")
        payload_sha256 = _sha256_hex(self.payload_sha256, "payload_sha256")
        if payload_sha256 != hashlib.sha256(self.payload).hexdigest():
            raise FiscalValidationError("payload_sha256 does not match payload")
        object.__setattr__(self, "payload_sha256", payload_sha256)
        _aware(self.created_at, "created_at")
        _aware(self.available_at, "available_at")
        if self.available_at < self.created_at:
            raise FiscalValidationError("available_at cannot be before created_at")
        if not isinstance(self.status, FiscalOutboxStatus):
            raise FiscalValidationError("status must be FiscalOutboxStatus")
        if not isinstance(self.attempt_count, int) or isinstance(self.attempt_count, bool):
            raise FiscalValidationError("attempt_count must be an integer")
        if self.attempt_count < 0:
            raise FiscalValidationError("attempt_count must be >= 0")
        if self.lease_until is not None:
            _aware(self.lease_until, "lease_until")
        if self.last_error is not None:
            object.__setattr__(
                self,
                "last_error",
                _required(self.last_error, "last_error", 1024),
            )
        if self.completion_reference is not None:
            object.__setattr__(
                self,
                "completion_reference",
                _required(self.completion_reference, "completion_reference", 512),
            )
        self._validate_state_shape()

    def _validate_state_shape(self) -> None:
        if self.status is FiscalOutboxStatus.PENDING:
            if self.lease_until is not None or self.last_error is not None:
                raise FiscalValidationError("pending outbox entry cannot have lease/error")
            if self.completion_reference is not None:
                raise FiscalValidationError("pending outbox entry cannot be completed")
        elif self.status is FiscalOutboxStatus.IN_FLIGHT:
            if self.lease_until is None:
                raise FiscalValidationError("in-flight outbox entry requires lease_until")
            if self.completion_reference is not None:
                raise FiscalValidationError("in-flight outbox entry cannot be completed")
        elif self.status is FiscalOutboxStatus.RETRY_WAIT:
            if self.lease_until is not None or self.last_error is None:
                raise FiscalValidationError("retry-wait entry requires error and no lease")
            if self.completion_reference is not None:
                raise FiscalValidationError("retry-wait entry cannot be completed")
        elif self.status is FiscalOutboxStatus.SUCCEEDED:
            if self.lease_until is not None or self.completion_reference is None:
                raise FiscalValidationError(
                    "succeeded outbox entry requires completion reference and no lease"
                )
        elif self.status is FiscalOutboxStatus.DEAD_LETTER:
            if self.lease_until is not None or self.last_error is None:
                raise FiscalValidationError("dead-letter entry requires error and no lease")
            if self.completion_reference is not None:
                raise FiscalValidationError("dead-letter entry cannot be completed")


@dataclass(frozen=True, slots=True)
class FiscalOutboxEnqueueResult:
    entry: FiscalOutboxEntry
    replay: bool


@dataclass(frozen=True, slots=True)
class FiscalDispatchResult:
    status: FiscalDispatchStatus
    reference: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, FiscalDispatchStatus):
            raise FiscalValidationError("status must be FiscalDispatchStatus")
        if self.reference is not None:
            object.__setattr__(
                self,
                "reference",
                _required(self.reference, "reference", 512),
            )
        if self.error is not None:
            object.__setattr__(self, "error", _required(self.error, "error", 1024))
        if self.status is FiscalDispatchStatus.SUCCEEDED:
            if self.reference is None or self.error is not None:
                raise FiscalValidationError("successful dispatch requires reference only")
        elif self.reference is not None or self.error is None:
            raise FiscalValidationError("failed dispatch requires error only")


class FiscalOutboxStore(Protocol):
    def enqueue(self, entry: FiscalOutboxEntry) -> FiscalOutboxEnqueueResult: ...

    def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease_duration: timedelta,
    ) -> tuple[FiscalOutboxEntry, ...]: ...

    def mark_succeeded(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        completion_reference: str,
    ) -> FiscalOutboxEntry: ...

    def reschedule(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        available_at: datetime,
        error: str,
    ) -> FiscalOutboxEntry: ...

    def dead_letter(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        error: str,
    ) -> FiscalOutboxEntry: ...

    def get(self, entry_id: str) -> FiscalOutboxEntry | None: ...


class FiscalOutboxHandler(Protocol):
    def dispatch(self, entry: FiscalOutboxEntry) -> FiscalDispatchResult: ...


class InMemoryFiscalOutboxStore:
    """Thread-safe reference store; production adapters must provide durable storage."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[str, FiscalOutboxEntry] = {}

    def enqueue(self, entry: FiscalOutboxEntry) -> FiscalOutboxEnqueueResult:
        if not isinstance(entry, FiscalOutboxEntry):
            raise FiscalValidationError("entry must be FiscalOutboxEntry")
        with self._lock:
            existing = self._entries.get(entry.entry_id)
            if existing is None:
                self._entries[entry.entry_id] = entry
                return FiscalOutboxEnqueueResult(entry=entry, replay=False)
            if (
                existing.scope != entry.scope
                or existing.operation != entry.operation
                or existing.deduplication_key != entry.deduplication_key
                or existing.payload_sha256 != entry.payload_sha256
                or existing.payload != entry.payload
            ):
                raise OutboxConflictError(
                    "outbox deduplication identity was reused with different content"
                )
            return FiscalOutboxEnqueueResult(entry=existing, replay=True)

    def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease_duration: timedelta,
    ) -> tuple[FiscalOutboxEntry, ...]:
        _aware(now, "now")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise FiscalValidationError("limit must be a positive integer")
        if lease_duration <= timedelta(0):
            raise FiscalValidationError("lease_duration must be positive")
        claimed: list[FiscalOutboxEntry] = []
        with self._lock:
            candidates = sorted(
                self._entries.values(),
                key=lambda item: (item.available_at, item.created_at, item.entry_id),
            )
            for entry in candidates:
                if len(claimed) >= limit:
                    break
                if not _is_claimable(entry, now):
                    continue
                updated = replace(
                    entry,
                    status=FiscalOutboxStatus.IN_FLIGHT,
                    attempt_count=entry.attempt_count + 1,
                    lease_until=now + lease_duration,
                    last_error=None,
                )
                self._entries[entry.entry_id] = updated
                claimed.append(updated)
        return tuple(claimed)

    def mark_succeeded(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        completion_reference: str,
    ) -> FiscalOutboxEntry:
        with self._lock:
            current = self._expect_in_flight(entry_id, expected_attempt)
            updated = replace(
                current,
                status=FiscalOutboxStatus.SUCCEEDED,
                lease_until=None,
                last_error=None,
                completion_reference=_required(
                    completion_reference,
                    "completion_reference",
                    512,
                ),
            )
            self._entries[current.entry_id] = updated
            return updated

    def reschedule(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        available_at: datetime,
        error: str,
    ) -> FiscalOutboxEntry:
        _aware(available_at, "available_at")
        with self._lock:
            current = self._expect_in_flight(entry_id, expected_attempt)
            updated = replace(
                current,
                status=FiscalOutboxStatus.RETRY_WAIT,
                available_at=available_at,
                lease_until=None,
                last_error=_required(error, "error", 1024),
                completion_reference=None,
            )
            self._entries[current.entry_id] = updated
            return updated

    def dead_letter(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        error: str,
    ) -> FiscalOutboxEntry:
        with self._lock:
            current = self._expect_in_flight(entry_id, expected_attempt)
            updated = replace(
                current,
                status=FiscalOutboxStatus.DEAD_LETTER,
                lease_until=None,
                last_error=_required(error, "error", 1024),
                completion_reference=None,
            )
            self._entries[current.entry_id] = updated
            return updated

    def get(self, entry_id: str) -> FiscalOutboxEntry | None:
        normalized = _sha256_hex(entry_id, "entry_id")
        with self._lock:
            return self._entries.get(normalized)

    def _expect_in_flight(
        self,
        entry_id: str,
        expected_attempt: int,
    ) -> FiscalOutboxEntry:
        normalized = _sha256_hex(entry_id, "entry_id")
        current = self._entries.get(normalized)
        if current is None:
            raise OutboxStateError("outbox entry does not exist")
        if current.status is not FiscalOutboxStatus.IN_FLIGHT:
            raise OutboxStateError("outbox entry is not in flight")
        if current.attempt_count != expected_attempt:
            raise OutboxStateError("outbox attempt version does not match")
        return current


class FiscalOutboxService:
    """Create immutable, deterministic outbox identities before persistence."""

    def __init__(self, store: FiscalOutboxStore) -> None:
        self._store = store

    def enqueue(
        self,
        *,
        scope: ExecutionScope,
        operation: str,
        deduplication_key: str,
        payload: bytes,
        created_at: datetime,
    ) -> FiscalOutboxEnqueueResult:
        if not isinstance(scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        operation = _required(operation, "operation", 128).lower()
        deduplication_key = _required(
            deduplication_key,
            "deduplication_key",
            512,
        )
        if not isinstance(payload, bytes) or not payload:
            raise FiscalValidationError("payload must be non-empty bytes")
        _aware(created_at, "created_at")
        entry_id = _build_entry_id(scope, operation, deduplication_key)
        entry = FiscalOutboxEntry(
            entry_id=entry_id,
            scope=scope,
            operation=operation,
            deduplication_key=deduplication_key,
            payload=payload,
            payload_sha256=hashlib.sha256(payload).hexdigest(),
            created_at=created_at,
            available_at=created_at,
        )
        return self._store.enqueue(entry)


class FiscalOutboxDispatcher:
    """Lease due entries and apply deterministic retry/dead-letter policy."""

    def __init__(
        self,
        *,
        store: FiscalOutboxStore,
        handler: FiscalOutboxHandler,
        retry_policy: FiscalRetryPolicy | None = None,
    ) -> None:
        self._store = store
        self._handler = handler
        self._policy = retry_policy or FiscalRetryPolicy()

    def run_once(
        self,
        *,
        now: datetime,
        limit: int = 10,
        lease_duration: timedelta = timedelta(seconds=60),
    ) -> tuple[FiscalOutboxEntry, ...]:
        claimed = self._store.claim_due(
            now=now,
            limit=limit,
            lease_duration=lease_duration,
        )
        outcomes: list[FiscalOutboxEntry] = []
        for entry in claimed:
            if entry.attempt_count > self._policy.max_attempts:
                outcomes.append(
                    self._store.dead_letter(
                        entry.entry_id,
                        expected_attempt=entry.attempt_count,
                        error="maximum retry attempts exceeded before dispatch",
                    )
                )
                continue
            result = self._handler.dispatch(entry)
            if not isinstance(result, FiscalDispatchResult):
                raise OutboxStateError("outbox handler must return FiscalDispatchResult")
            if result.status is FiscalDispatchStatus.SUCCEEDED:
                assert result.reference is not None
                outcomes.append(
                    self._store.mark_succeeded(
                        entry.entry_id,
                        expected_attempt=entry.attempt_count,
                        completion_reference=result.reference,
                    )
                )
            elif result.status is FiscalDispatchStatus.FATAL_FAILURE:
                assert result.error is not None
                outcomes.append(
                    self._store.dead_letter(
                        entry.entry_id,
                        expected_attempt=entry.attempt_count,
                        error=result.error,
                    )
                )
            elif entry.attempt_count >= self._policy.max_attempts:
                assert result.error is not None
                outcomes.append(
                    self._store.dead_letter(
                        entry.entry_id,
                        expected_attempt=entry.attempt_count,
                        error=result.error,
                    )
                )
            else:
                assert result.error is not None
                outcomes.append(
                    self._store.reschedule(
                        entry.entry_id,
                        expected_attempt=entry.attempt_count,
                        available_at=now
                        + self._policy.delay_for_attempt(entry.attempt_count),
                        error=result.error,
                    )
                )
        return tuple(outcomes)


def _build_entry_id(
    scope: ExecutionScope,
    operation: str,
    deduplication_key: str,
) -> str:
    material = "|".join(
        (
            scope.tenant_id,
            scope.unit_id,
            scope.environment.value,
            operation,
            deduplication_key,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _is_claimable(entry: FiscalOutboxEntry, now: datetime) -> bool:
    if entry.status in {FiscalOutboxStatus.PENDING, FiscalOutboxStatus.RETRY_WAIT}:
        return entry.available_at <= now
    if entry.status is FiscalOutboxStatus.IN_FLIGHT:
        return entry.lease_until is not None and entry.lease_until <= now
    return False
