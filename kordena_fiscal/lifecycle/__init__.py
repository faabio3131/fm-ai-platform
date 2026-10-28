"""Public lifecycle and issuance-idempotency surface."""

from .idempotency import (
    IdempotencyConflictError,
    IdempotencyCoordinator,
    IdempotencyKey,
    IdempotencyReservation,
    IdempotencyStateError,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    IssuanceAttempt,
    IssuanceAttemptStatus,
    build_issuance_key,
    build_request_fingerprint,
)
from .state_machine import (
    FiscalDocumentState,
    FiscalStateMachine,
    FiscalStateSnapshot,
    FiscalStateTransition,
    InvalidFiscalTransitionError,
)

__all__ = [
    "FiscalDocumentState",
    "FiscalStateMachine",
    "FiscalStateSnapshot",
    "FiscalStateTransition",
    "IdempotencyConflictError",
    "IdempotencyCoordinator",
    "IdempotencyKey",
    "IdempotencyReservation",
    "IdempotencyStateError",
    "IdempotencyStore",
    "InMemoryIdempotencyStore",
    "InvalidFiscalTransitionError",
    "IssuanceAttempt",
    "IssuanceAttemptStatus",
    "build_issuance_key",
    "build_request_fingerprint",
]
