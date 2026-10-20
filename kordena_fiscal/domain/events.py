"""Canonical domain-event metadata for the fiscal engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import FiscalValidationError
from .primitives import ExecutionScope, SourceReference, _required_text


@dataclass(frozen=True, slots=True)
class FiscalDomainEvent:
    """Immutable metadata envelope for auditable fiscal-domain events.

    Event payloads are intentionally modeled by typed objects in later blocks. This
    envelope carries only stable metadata shared by all fiscal events.
    """

    event_id: str
    event_type: str
    aggregate_id: str
    source: SourceReference
    scope: ExecutionScope
    occurred_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "event_id",
            _required_text(self.event_id, "event_id", max_length=128),
        )
        object.__setattr__(
            self,
            "event_type",
            _required_text(self.event_type, "event_type", max_length=128),
        )
        object.__setattr__(
            self,
            "aggregate_id",
            _required_text(self.aggregate_id, "aggregate_id", max_length=128),
        )
        if not isinstance(self.source, SourceReference):
            raise FiscalValidationError("source must be a SourceReference")
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be an ExecutionScope")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise FiscalValidationError("occurred_at must be timezone-aware")
        if self.schema_version < 1:
            raise FiscalValidationError("schema_version must be >= 1")
