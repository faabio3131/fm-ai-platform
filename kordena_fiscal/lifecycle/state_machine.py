"""Explicit, audited lifecycle for one fiscal document attempt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kordena_fiscal.domain import FiscalDomainError, FiscalValidationError


class FiscalDocumentState(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    READY_TO_SIGN = "ready_to_sign"
    SIGNING = "signing"
    READY_TO_TRANSMIT = "ready_to_transmit"
    TRANSMITTING = "transmitting"
    AUTHORIZED = "authorized"
    REJECTED = "rejected"
    CONTINGENCY = "contingency"
    CONTINGENCY_PENDING = "contingency_pending"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    ERROR = "error"


class InvalidFiscalTransitionError(FiscalDomainError):
    """Raised when a lifecycle transition is not allowed by the state graph."""


_ALLOWED_TRANSITIONS: dict[FiscalDocumentState, frozenset[FiscalDocumentState]] = {
    FiscalDocumentState.DRAFT: frozenset({FiscalDocumentState.VALIDATING}),
    FiscalDocumentState.VALIDATING: frozenset(
        {
            FiscalDocumentState.READY_TO_SIGN,
            FiscalDocumentState.REJECTED,
            FiscalDocumentState.ERROR,
        }
    ),
    FiscalDocumentState.READY_TO_SIGN: frozenset(
        {FiscalDocumentState.SIGNING, FiscalDocumentState.ERROR}
    ),
    FiscalDocumentState.SIGNING: frozenset(
        {FiscalDocumentState.READY_TO_TRANSMIT, FiscalDocumentState.ERROR}
    ),
    FiscalDocumentState.READY_TO_TRANSMIT: frozenset(
        {
            FiscalDocumentState.TRANSMITTING,
            FiscalDocumentState.CONTINGENCY,
            FiscalDocumentState.ERROR,
        }
    ),
    FiscalDocumentState.TRANSMITTING: frozenset(
        {
            FiscalDocumentState.AUTHORIZED,
            FiscalDocumentState.REJECTED,
            FiscalDocumentState.CONTINGENCY,
            FiscalDocumentState.ERROR,
        }
    ),
    FiscalDocumentState.CONTINGENCY: frozenset(
        {FiscalDocumentState.CONTINGENCY_PENDING, FiscalDocumentState.ERROR}
    ),
    FiscalDocumentState.CONTINGENCY_PENDING: frozenset(
        {FiscalDocumentState.TRANSMITTING, FiscalDocumentState.ERROR}
    ),
    FiscalDocumentState.AUTHORIZED: frozenset({FiscalDocumentState.CANCEL_REQUESTED}),
    FiscalDocumentState.CANCEL_REQUESTED: frozenset(
        {
            FiscalDocumentState.CANCELLED,
            FiscalDocumentState.AUTHORIZED,
            FiscalDocumentState.ERROR,
        }
    ),
    FiscalDocumentState.REJECTED: frozenset(),
    FiscalDocumentState.CANCELLED: frozenset(),
    FiscalDocumentState.ERROR: frozenset(),
}


def _required_text(value: str, field_name: str, max_length: int = 500) -> str:
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


@dataclass(frozen=True, slots=True)
class FiscalStateTransition:
    """One immutable transition in a fiscal-attempt audit trail."""

    sequence: int
    from_state: FiscalDocumentState
    to_state: FiscalDocumentState
    occurred_at: datetime
    reason: str
    correlation_id: str

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise FiscalValidationError("transition sequence must be >= 1")
        if not isinstance(self.from_state, FiscalDocumentState):
            raise FiscalValidationError("from_state must be FiscalDocumentState")
        if not isinstance(self.to_state, FiscalDocumentState):
            raise FiscalValidationError("to_state must be FiscalDocumentState")
        _aware(self.occurred_at, "occurred_at")
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        object.__setattr__(
            self,
            "correlation_id",
            _required_text(self.correlation_id, "correlation_id", 256),
        )


@dataclass(frozen=True, slots=True)
class FiscalStateSnapshot:
    """Validated current state plus complete immutable transition history."""

    document_id: str
    state: FiscalDocumentState
    version: int
    updated_at: datetime
    history: tuple[FiscalStateTransition, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "document_id",
            _required_text(self.document_id, "document_id", 128),
        )
        if not isinstance(self.state, FiscalDocumentState):
            raise FiscalValidationError("state must be FiscalDocumentState")
        _aware(self.updated_at, "updated_at")
        if self.version < 0:
            raise FiscalValidationError("state version must be >= 0")
        if self.version != len(self.history):
            raise FiscalValidationError("state version must equal transition history length")

        if not self.history:
            if self.version != 0 or self.state is not FiscalDocumentState.DRAFT:
                raise FiscalValidationError(
                    "empty state history is valid only for DRAFT version 0"
                )
            return

        previous_state = FiscalDocumentState.DRAFT
        previous_time: datetime | None = None
        for expected_sequence, transition in enumerate(self.history, start=1):
            if not isinstance(transition, FiscalStateTransition):
                raise FiscalValidationError(
                    "history must contain FiscalStateTransition values"
                )
            if transition.sequence != expected_sequence:
                raise FiscalValidationError("transition history sequence is not contiguous")
            if transition.from_state is not previous_state:
                raise FiscalValidationError("transition history state chain is inconsistent")
            if transition.to_state not in _ALLOWED_TRANSITIONS[transition.from_state]:
                raise FiscalValidationError("transition history contains an invalid transition")
            if previous_time is not None and transition.occurred_at < previous_time:
                raise FiscalValidationError("transition history time must be monotonic")
            previous_state = transition.to_state
            previous_time = transition.occurred_at

        if previous_state is not self.state:
            raise FiscalValidationError("snapshot state must equal final transition state")
        if self.updated_at != self.history[-1].occurred_at:
            raise FiscalValidationError(
                "updated_at must equal the latest transition occurred_at"
            )

    @classmethod
    def initial(cls, document_id: str, created_at: datetime) -> FiscalStateSnapshot:
        return cls(
            document_id=document_id,
            state=FiscalDocumentState.DRAFT,
            version=0,
            updated_at=_aware(created_at, "created_at"),
        )


class FiscalStateMachine:
    """Apply only transitions explicitly permitted by the fiscal lifecycle graph."""

    def transition(
        self,
        snapshot: FiscalStateSnapshot,
        target: FiscalDocumentState,
        *,
        occurred_at: datetime,
        reason: str,
        correlation_id: str,
    ) -> FiscalStateSnapshot:
        if not isinstance(snapshot, FiscalStateSnapshot):
            raise FiscalValidationError("snapshot must be FiscalStateSnapshot")
        if not isinstance(target, FiscalDocumentState):
            raise FiscalValidationError("target must be FiscalDocumentState")
        _aware(occurred_at, "occurred_at")
        if occurred_at < snapshot.updated_at:
            raise FiscalValidationError("transition time cannot move backwards")
        if target not in _ALLOWED_TRANSITIONS[snapshot.state]:
            raise InvalidFiscalTransitionError(
                f"transition {snapshot.state.value} -> {target.value} is not allowed"
            )

        transition = FiscalStateTransition(
            sequence=snapshot.version + 1,
            from_state=snapshot.state,
            to_state=target,
            occurred_at=occurred_at,
            reason=reason,
            correlation_id=correlation_id,
        )
        return FiscalStateSnapshot(
            document_id=snapshot.document_id,
            state=target,
            version=snapshot.version + 1,
            updated_at=occurred_at,
            history=(*snapshot.history, transition),
        )

    def allowed_targets(
        self,
        state: FiscalDocumentState,
    ) -> frozenset[FiscalDocumentState]:
        if not isinstance(state, FiscalDocumentState):
            raise FiscalValidationError("state must be FiscalDocumentState")
        return _ALLOWED_TRANSITIONS[state]
