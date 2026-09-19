"""Durable SQLAlchemy adapters for the frozen Fiscal V1 persistence ports."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from infra.fiscal.modelos_orm import (
    FiscalArchiveORM,
    FiscalIdempotencyORM,
    FiscalOutboxORM,
    FiscalSequenceORM,
)
from kordena_fiscal.archive.records import (
    ArchiveConflictError,
    FiscalArchiveEntry,
    FiscalArchiveKind,
    RetentionPolicyMetadata,
)
from kordena_fiscal.contingency.outbox import (
    FiscalOutboxEnqueueResult,
    FiscalOutboxEntry,
    FiscalOutboxStatus,
    OutboxConflictError,
    OutboxStateError,
)
from kordena_fiscal.domain import (
    ExecutionScope,
    FiscalEnvironment,
    FiscalValidationError,
)
from kordena_fiscal.lifecycle.idempotency import (
    IdempotencyConflictError,
    IdempotencyKey,
    IdempotencyReservation,
    IdempotencyStateError,
    IssuanceAttempt,
    IssuanceAttemptStatus,
)
from kordena_fiscal.numbering.manager import (
    FiscalNumberReservation,
    FiscalSequenceKey,
    FiscalSequencePolicy,
    SequenceExhaustedError,
    SequenceStateError,
)

SessionFactory = Callable[[], Session]


def _db_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reservation_token(key: FiscalSequenceKey, number: int) -> str:
    material = f"{key.canonical_material}|{number}".encode()
    return hashlib.sha256(material).hexdigest()


def _required_outbox_text(value: str, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise FiscalValidationError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise FiscalValidationError(f"{field_name} exceeds max length {max_length}")
    return normalized


def _outbox_entry_id(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise FiscalValidationError("entry_id must be SHA-256 hex")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise FiscalValidationError("entry_id must be hexadecimal") from exc
    return normalized


class FiscalSequenceStoreSQLAlchemy:
    """Atomic fiscal numbering store partitioned by scope, model and series."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _identity(key: FiscalSequenceKey) -> tuple[ColumnElement[bool], ...]:
        return (
            FiscalSequenceORM.tenant_id == key.tenant_id,
            FiscalSequenceORM.unit_id == key.unit_id,
            FiscalSequenceORM.environment == key.environment.value,
            FiscalSequenceORM.model == int(key.model.value),
            FiscalSequenceORM.series == key.series,
        )

    def reserve_next(
        self,
        key: FiscalSequenceKey,
        policy: FiscalSequencePolicy,
    ) -> FiscalNumberReservation:
        if not isinstance(key, FiscalSequenceKey):
            raise FiscalValidationError("key must be FiscalSequenceKey")
        if not isinstance(policy, FiscalSequencePolicy):
            raise FiscalValidationError("policy must be FiscalSequencePolicy")

        for retry in range(3):
            try:
                with self._session_factory() as session, session.begin():
                    row = session.execute(
                        select(FiscalSequenceORM)
                        .where(*self._identity(key))
                        .with_for_update()
                    ).scalar_one_or_none()
                    if row is None:
                        candidate = policy.first_number
                        row = FiscalSequenceORM(
                            tenant_id=key.tenant_id,
                            unit_id=key.unit_id,
                            environment=key.environment.value,
                            model=int(key.model.value),
                            series=key.series,
                            first_number=policy.first_number,
                            max_number=policy.max_number,
                            last_number=candidate,
                            version=1,
                        )
                        session.add(row)
                        session.flush()
                    else:
                        stored = FiscalSequencePolicy(
                            first_number=row.first_number,
                            max_number=row.max_number,
                        )
                        if stored != policy:
                            raise SequenceStateError(
                                "sequence policy cannot change after the first reservation"
                            )
                        candidate = row.last_number + 1
                        if policy.max_number is not None and candidate > policy.max_number:
                            raise SequenceExhaustedError(
                                "fiscal sequence has reached its configured maximum"
                            )
                        row.last_number = candidate
                        row.version += 1
                        session.flush()
                    return FiscalNumberReservation(
                        key=key,
                        number=candidate,
                        reservation_token=_reservation_token(key, candidate),
                    )
            except IntegrityError:
                if retry == 2:
                    raise
        raise RuntimeError("unreachable fiscal sequence retry state")

    def last_reserved(self, key: FiscalSequenceKey) -> int | None:
        if not isinstance(key, FiscalSequenceKey):
            raise FiscalValidationError("key must be FiscalSequenceKey")
        with self._session_factory() as session:
            row = session.execute(
                select(FiscalSequenceORM).where(*self._identity(key))
            ).scalar_one_or_none()
            return None if row is None else row.last_number


class IdempotencyStoreSQLAlchemy:
    """Durable issuance idempotency preserving Fiscal V1 generation semantics."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_domain(row: FiscalIdempotencyORM) -> IssuanceAttempt:
        return IssuanceAttempt(
            key=IdempotencyKey(row.key_value),
            generation=row.generation,
            request_fingerprint=row.request_fingerprint,
            document_id=row.document_id,
            status=IssuanceAttemptStatus(row.status),
            result_reference=row.result_reference,
            rejection_reason=row.rejection_reason,
        )

    def _latest(
        self,
        session: Session,
        key: IdempotencyKey,
        *,
        lock: bool,
    ) -> FiscalIdempotencyORM | None:
        query = (
            select(FiscalIdempotencyORM)
            .where(FiscalIdempotencyORM.key_value == key.value)
            .order_by(FiscalIdempotencyORM.generation.desc())
            .limit(1)
        )
        if lock:
            query = query.with_for_update()
        return session.execute(query).scalar_one_or_none()

    def reserve(
        self,
        key: IdempotencyKey,
        request_fingerprint: str,
        document_id: str,
    ) -> IdempotencyReservation:
        for retry in range(3):
            try:
                with self._session_factory() as session, session.begin():
                    latest = self._latest(session, key, lock=True)
                    if latest is None:
                        row = FiscalIdempotencyORM(
                            key_value=key.value,
                            generation=1,
                            request_fingerprint=request_fingerprint,
                            document_id=document_id,
                            status=IssuanceAttemptStatus.RESERVED.value,
                        )
                        session.add(row)
                        session.flush()
                        return IdempotencyReservation(
                            attempt=self._to_domain(row),
                            replay=False,
                        )
                    attempt = self._to_domain(latest)
                    if attempt.request_fingerprint == request_fingerprint:
                        return IdempotencyReservation(attempt=attempt, replay=True)
                    if attempt.status is not IssuanceAttemptStatus.REJECTED:
                        raise IdempotencyConflictError(
                            "issuance intent already exists with different content "
                            "and is not safely rejected"
                        )
                    row = FiscalIdempotencyORM(
                        key_value=key.value,
                        generation=attempt.generation + 1,
                        request_fingerprint=request_fingerprint,
                        document_id=document_id,
                        status=IssuanceAttemptStatus.RESERVED.value,
                    )
                    session.add(row)
                    session.flush()
                    return IdempotencyReservation(
                        attempt=self._to_domain(row),
                        replay=False,
                    )
            except IntegrityError:
                if retry == 2:
                    raise
        raise RuntimeError("unreachable idempotency retry state")

    def _transition(
        self,
        key: IdempotencyKey,
        generation: int,
        *,
        target: IssuanceAttemptStatus,
        result_reference: str | None = None,
        rejection_reason: str | None = None,
    ) -> IssuanceAttempt:
        with self._session_factory() as session, session.begin():
            latest = self._latest(session, key, lock=True)
            if latest is None:
                raise IdempotencyStateError(
                    "idempotency key has no reserved attempt"
                )
            if latest.generation != generation:
                raise IdempotencyStateError(
                    "only the latest generation can be updated"
                )
            current = self._to_domain(latest)
            if current.status is target:
                expected = (
                    current.result_reference
                    if target is IssuanceAttemptStatus.AUTHORIZED
                    else current.rejection_reason
                )
                supplied = (
                    result_reference
                    if target is IssuanceAttemptStatus.AUTHORIZED
                    else rejection_reason
                )
                if expected != supplied:
                    raise IdempotencyStateError(
                        "terminal idempotency result cannot change"
                    )
                return current
            if current.status is not IssuanceAttemptStatus.RESERVED:
                raise IdempotencyStateError(
                    "only reserved attempt can become terminal"
                )
            latest.status = target.value
            latest.result_reference = result_reference
            latest.rejection_reason = rejection_reason
            session.flush()
            return self._to_domain(latest)

    def mark_authorized(
        self,
        key: IdempotencyKey,
        generation: int,
        result_reference: str,
    ) -> IssuanceAttempt:
        reference = result_reference.strip()
        if not reference:
            raise FiscalValidationError("result_reference must not be blank")
        return self._transition(
            key,
            generation,
            target=IssuanceAttemptStatus.AUTHORIZED,
            result_reference=reference,
        )

    def mark_rejected(
        self,
        key: IdempotencyKey,
        generation: int,
        rejection_reason: str,
    ) -> IssuanceAttempt:
        reason = rejection_reason.strip()
        if not reason:
            raise FiscalValidationError("rejection_reason must not be blank")
        return self._transition(
            key,
            generation,
            target=IssuanceAttemptStatus.REJECTED,
            rejection_reason=reason,
        )

    def attempts(self, key: IdempotencyKey) -> tuple[IssuanceAttempt, ...]:
        with self._session_factory() as session:
            rows = session.execute(
                select(FiscalIdempotencyORM)
                .where(FiscalIdempotencyORM.key_value == key.value)
                .order_by(FiscalIdempotencyORM.generation)
            ).scalars()
            return tuple(self._to_domain(row) for row in rows)


class FiscalOutboxStoreSQLAlchemy:
    """Durable outbox with lease-based claim/retry semantics."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_domain(row: FiscalOutboxORM) -> FiscalOutboxEntry:
        created_at = _db_datetime(row.created_at)
        available_at = _db_datetime(row.available_at)
        assert created_at is not None and available_at is not None
        return FiscalOutboxEntry(
            entry_id=row.entry_id,
            scope=ExecutionScope(
                tenant_id=row.tenant_id,
                unit_id=row.unit_id,
                environment=FiscalEnvironment(row.environment),
                correlation_id=row.correlation_id,
            ),
            operation=row.operation,
            deduplication_key=row.deduplication_key,
            payload=bytes(row.payload),
            payload_sha256=row.payload_sha256,
            created_at=created_at,
            available_at=available_at,
            status=FiscalOutboxStatus(row.status),
            attempt_count=row.attempt_count,
            lease_until=_db_datetime(row.lease_until),
            last_error=row.last_error,
            completion_reference=row.completion_reference,
        )

    @staticmethod
    def _same(existing: FiscalOutboxEntry, incoming: FiscalOutboxEntry) -> bool:
        return (
            existing.scope == incoming.scope
            and existing.operation == incoming.operation
            and existing.deduplication_key == incoming.deduplication_key
            and existing.payload_sha256 == incoming.payload_sha256
            and existing.payload == incoming.payload
        )

    def enqueue(self, entry: FiscalOutboxEntry) -> FiscalOutboxEnqueueResult:
        if not isinstance(entry, FiscalOutboxEntry):
            raise FiscalValidationError("entry must be FiscalOutboxEntry")
        try:
            with self._session_factory() as session, session.begin():
                existing_row = session.get(FiscalOutboxORM, entry.entry_id)
                if existing_row is not None:
                    existing = self._to_domain(existing_row)
                    if not self._same(existing, entry):
                        raise OutboxConflictError(
                            "outbox deduplication identity was reused "
                            "with different content"
                        )
                    return FiscalOutboxEnqueueResult(entry=existing, replay=True)
                session.add(
                    FiscalOutboxORM(
                        entry_id=entry.entry_id,
                        tenant_id=entry.scope.tenant_id,
                        unit_id=entry.scope.unit_id,
                        environment=entry.scope.environment.value,
                        correlation_id=entry.scope.correlation_id,
                        operation=entry.operation,
                        deduplication_key=entry.deduplication_key,
                        payload=entry.payload,
                        payload_sha256=entry.payload_sha256,
                        created_at=entry.created_at,
                        available_at=entry.available_at,
                        status=entry.status.value,
                        attempt_count=entry.attempt_count,
                        lease_until=entry.lease_until,
                        last_error=entry.last_error,
                        completion_reference=entry.completion_reference,
                    )
                )
                session.flush()
                return FiscalOutboxEnqueueResult(entry=entry, replay=False)
        except IntegrityError as exc:
            with self._session_factory() as session:
                row = session.get(FiscalOutboxORM, entry.entry_id)
                if row is not None and self._same(self._to_domain(row), entry):
                    return FiscalOutboxEnqueueResult(
                        entry=self._to_domain(row),
                        replay=True,
                    )
            raise OutboxConflictError(
                "outbox identity already exists with different content"
            ) from exc

    def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        lease_duration: timedelta,
    ) -> tuple[FiscalOutboxEntry, ...]:
        if now.tzinfo is None or now.utcoffset() is None:
            raise FiscalValidationError("now must be timezone-aware")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise FiscalValidationError("limit must be a positive integer")
        if lease_duration <= timedelta(0):
            raise FiscalValidationError("lease_duration must be positive")
        with self._session_factory() as session, session.begin():
            due = or_(
                and_(
                    FiscalOutboxORM.status.in_(
                        (
                            FiscalOutboxStatus.PENDING.value,
                            FiscalOutboxStatus.RETRY_WAIT.value,
                        )
                    ),
                    FiscalOutboxORM.available_at <= now,
                ),
                and_(
                    FiscalOutboxORM.status == FiscalOutboxStatus.IN_FLIGHT.value,
                    FiscalOutboxORM.lease_until.is_not(None),
                    FiscalOutboxORM.lease_until <= now,
                ),
            )
            rows = tuple(
                session.execute(
                    select(FiscalOutboxORM)
                    .where(due)
                    .order_by(
                        FiscalOutboxORM.available_at,
                        FiscalOutboxORM.created_at,
                        FiscalOutboxORM.entry_id,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                ).scalars()
            )
            claimed: list[FiscalOutboxEntry] = []
            for row in rows:
                row.status = FiscalOutboxStatus.IN_FLIGHT.value
                row.attempt_count += 1
                row.lease_until = now + lease_duration
                row.last_error = None
                row.completion_reference = None
                session.flush()
                claimed.append(self._to_domain(row))
            return tuple(claimed)

    def _locked(self, session: Session, entry_id: str) -> FiscalOutboxORM:
        normalized = _outbox_entry_id(entry_id)
        row = session.execute(
            select(FiscalOutboxORM)
            .where(FiscalOutboxORM.entry_id == normalized)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise OutboxStateError("outbox entry does not exist")
        return row

    @staticmethod
    def _assert_in_flight(row: FiscalOutboxORM, expected_attempt: int) -> None:
        if row.status != FiscalOutboxStatus.IN_FLIGHT.value:
            raise OutboxStateError("outbox entry is not in flight")
        if row.attempt_count != expected_attempt:
            raise OutboxStateError("outbox attempt version does not match")

    def mark_succeeded(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        completion_reference: str,
    ) -> FiscalOutboxEntry:
        with self._session_factory() as session, session.begin():
            row = self._locked(session, entry_id)
            self._assert_in_flight(row, expected_attempt)
            reference = _required_outbox_text(
                completion_reference,
                "completion_reference",
                512,
            )
            row.status = FiscalOutboxStatus.SUCCEEDED.value
            row.lease_until = None
            row.last_error = None
            row.completion_reference = reference
            session.flush()
            return self._to_domain(row)

    def reschedule(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        available_at: datetime,
        error: str,
    ) -> FiscalOutboxEntry:
        if available_at.tzinfo is None or available_at.utcoffset() is None:
            raise FiscalValidationError("available_at must be timezone-aware")
        with self._session_factory() as session, session.begin():
            row = self._locked(session, entry_id)
            self._assert_in_flight(row, expected_attempt)
            message = _required_outbox_text(error, "error", 1024)
            row.status = FiscalOutboxStatus.RETRY_WAIT.value
            row.available_at = available_at
            row.lease_until = None
            row.last_error = message
            row.completion_reference = None
            session.flush()
            return self._to_domain(row)

    def dead_letter(
        self,
        entry_id: str,
        *,
        expected_attempt: int,
        error: str,
    ) -> FiscalOutboxEntry:
        with self._session_factory() as session, session.begin():
            row = self._locked(session, entry_id)
            self._assert_in_flight(row, expected_attempt)
            message = _required_outbox_text(error, "error", 1024)
            row.status = FiscalOutboxStatus.DEAD_LETTER.value
            row.lease_until = None
            row.last_error = message
            row.completion_reference = None
            session.flush()
            return self._to_domain(row)

    def get(self, entry_id: str) -> FiscalOutboxEntry | None:
        normalized = _outbox_entry_id(entry_id)
        with self._session_factory() as session:
            row = session.get(FiscalOutboxORM, normalized)
            return None if row is None else self._to_domain(row)


class FiscalArchiveStoreSQLAlchemy:
    """Append-only archive adapter preserving exact artifact identity and scope."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _to_domain(row: FiscalArchiveORM) -> FiscalArchiveEntry:
        archived_at = _db_datetime(row.archived_at)
        retain_until = _db_datetime(row.retain_until)
        assert archived_at is not None
        return FiscalArchiveEntry(
            entry_id=row.entry_id,
            scope=ExecutionScope(
                tenant_id=row.tenant_id,
                unit_id=row.unit_id,
                environment=FiscalEnvironment(row.environment),
                correlation_id=row.correlation_id,
            ),
            document_reference=row.document_reference,
            kind=FiscalArchiveKind(row.kind),
            content=bytes(row.content),
            content_sha256=row.content_sha256,
            media_type=row.media_type,
            archived_at=archived_at,
            retention=RetentionPolicyMetadata(
                policy_id=row.retention_policy_id,
                policy_version=row.retention_policy_version,
                retain_until=retain_until,
                legal_basis_reference=row.legal_basis_reference,
            ),
            previous_manifest_sha256=row.previous_manifest_sha256,
        )

    def append(self, entry: FiscalArchiveEntry) -> FiscalArchiveEntry:
        if not isinstance(entry, FiscalArchiveEntry):
            raise FiscalValidationError("entry must be FiscalArchiveEntry")
        try:
            with self._session_factory() as session, session.begin():
                row = session.get(FiscalArchiveORM, entry.entry_id)
                if row is not None:
                    existing = self._to_domain(row)
                    if existing != entry:
                        raise ArchiveConflictError(
                            "archive entry identity already exists with other content"
                        )
                    return existing
                session.add(
                    FiscalArchiveORM(
                        entry_id=entry.entry_id,
                        tenant_id=entry.scope.tenant_id,
                        unit_id=entry.scope.unit_id,
                        environment=entry.scope.environment.value,
                        correlation_id=entry.scope.correlation_id,
                        document_reference=entry.document_reference,
                        kind=entry.kind.value,
                        content=entry.content,
                        content_sha256=entry.content_sha256,
                        media_type=entry.media_type,
                        archived_at=entry.archived_at,
                        retention_policy_id=entry.retention.policy_id,
                        retention_policy_version=entry.retention.policy_version,
                        retain_until=entry.retention.retain_until,
                        legal_basis_reference=entry.retention.legal_basis_reference,
                        previous_manifest_sha256=entry.previous_manifest_sha256,
                    )
                )
                session.flush()
                return entry
        except IntegrityError as exc:
            with self._session_factory() as session:
                row = session.get(FiscalArchiveORM, entry.entry_id)
                if row is not None and self._to_domain(row) == entry:
                    return self._to_domain(row)
            raise ArchiveConflictError(
                "archive entry identity already exists with other content"
            ) from exc

    def get(self, entry_id: str) -> FiscalArchiveEntry | None:
        with self._session_factory() as session:
            row = session.get(FiscalArchiveORM, entry_id)
            return None if row is None else self._to_domain(row)

    def list_for_document(
        self,
        scope: ExecutionScope,
        document_reference: str,
    ) -> tuple[FiscalArchiveEntry, ...]:
        with self._session_factory() as session:
            rows = session.execute(
                select(FiscalArchiveORM)
                .where(
                    FiscalArchiveORM.tenant_id == scope.tenant_id,
                    FiscalArchiveORM.unit_id == scope.unit_id,
                    FiscalArchiveORM.environment == scope.environment.value,
                    FiscalArchiveORM.document_reference == document_reference,
                )
                .order_by(
                    FiscalArchiveORM.archived_at,
                    FiscalArchiveORM.entry_id,
                )
            ).scalars()
            return tuple(self._to_domain(row) for row in rows)
