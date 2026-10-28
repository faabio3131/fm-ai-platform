"""Deterministic reconciliation of one settled sale against fiscal attempts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kordena_fiscal.documents import CanonicalFiscalDocument
from kordena_fiscal.domain import (
    ExecutionScope,
    FiscalDomainError,
    FiscalValidationError,
    Money,
    SourceReference,
)
from kordena_fiscal.lifecycle import FiscalDocumentState


class ReconciliationContractError(FiscalDomainError):
    """Raised when reconciliation inputs cross an identity or scope boundary."""


class ReconciliationStatus(StrEnum):
    MATCHED = "matched"
    PENDING = "pending"
    DIVERGENT = "divergent"


class ReconciliationIssueCode(StrEnum):
    HOST_PAYMENT_MISMATCH = "host_payment_mismatch"
    MISSING_AUTHORIZED_FISCAL_DOCUMENT = "missing_authorized_fiscal_document"
    FISCAL_PROCESSING_PENDING = "fiscal_processing_pending"
    CLOSED_SALE_WITH_CANCELLED_FISCAL = "closed_sale_with_cancelled_fiscal"
    DUPLICATE_AUTHORIZED_FISCAL_DOCUMENT = "duplicate_authorized_fiscal_document"
    PARALLEL_FISCAL_ATTEMPT = "parallel_fiscal_attempt"
    SALE_FISCAL_TOTAL_MISMATCH = "sale_fiscal_total_mismatch"
    FISCAL_PAYMENT_MISMATCH = "fiscal_payment_mismatch"
    PAYMENT_SNAPSHOT_MISMATCH = "payment_snapshot_mismatch"


_PENDING_STATES = frozenset(
    {
        FiscalDocumentState.DRAFT,
        FiscalDocumentState.VALIDATING,
        FiscalDocumentState.READY_TO_SIGN,
        FiscalDocumentState.SIGNING,
        FiscalDocumentState.READY_TO_TRANSMIT,
        FiscalDocumentState.TRANSMITTING,
        FiscalDocumentState.CONTINGENCY,
        FiscalDocumentState.CONTINGENCY_PENDING,
        FiscalDocumentState.CANCEL_REQUESTED,
    }
)


def _required(value: str, field_name: str, max_length: int = 256) -> str:
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


def _validate_money(value: Money, field_name: str) -> Money:
    if not isinstance(value, Money):
        raise FiscalValidationError(f"{field_name} must be Money")
    if value.amount < 0:
        raise FiscalValidationError(f"{field_name} must be non-negative")
    return value


@dataclass(frozen=True, slots=True)
class HostSettlementSnapshot:
    """Authoritative host snapshot for one sale considered financially settled."""

    scope: ExecutionScope
    source: SourceReference
    sale_amount: Money
    payment_amount: Money
    change_amount: Money
    settled_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.source, SourceReference):
            raise FiscalValidationError("source must be SourceReference")
        _validate_money(self.sale_amount, "sale_amount")
        _validate_money(self.payment_amount, "payment_amount")
        _validate_money(self.change_amount, "change_amount")
        if self.change_amount.amount > self.payment_amount.amount:
            raise FiscalValidationError("change_amount cannot exceed payment_amount")
        _aware(self.settled_at, "settled_at")

    @property
    def settled_payment_amount(self) -> Money:
        return self.payment_amount - self.change_amount


@dataclass(frozen=True, slots=True)
class FiscalReconciliationCandidate:
    """Minimal immutable fiscal attempt projection used by reconciliation."""

    document_id: str
    scope: ExecutionScope
    source: SourceReference
    state: FiscalDocumentState
    net_amount: Money
    payment_amount: Money
    change_amount: Money

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_id", _required(self.document_id, "document_id", 128))
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.source, SourceReference):
            raise FiscalValidationError("source must be SourceReference")
        if not isinstance(self.state, FiscalDocumentState):
            raise FiscalValidationError("state must be FiscalDocumentState")
        _validate_money(self.net_amount, "net_amount")
        _validate_money(self.payment_amount, "payment_amount")
        _validate_money(self.change_amount, "change_amount")
        if self.change_amount.amount > self.payment_amount.amount:
            raise FiscalValidationError("change_amount cannot exceed payment_amount")

    @classmethod
    def from_document(
        cls,
        document: CanonicalFiscalDocument,
        state: FiscalDocumentState,
    ) -> FiscalReconciliationCandidate:
        if not isinstance(document, CanonicalFiscalDocument):
            raise FiscalValidationError("document must be CanonicalFiscalDocument")
        if not isinstance(state, FiscalDocumentState):
            raise FiscalValidationError("state must be FiscalDocumentState")
        totals = document.totals
        return cls(
            document_id=document.document_id,
            scope=document.scope,
            source=document.source,
            state=state,
            net_amount=totals.net_amount,
            payment_amount=totals.payment_amount,
            change_amount=totals.change_amount,
        )

    @property
    def settled_payment_amount(self) -> Money:
        return self.payment_amount - self.change_amount


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    code: ReconciliationIssueCode
    message: str
    document_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code, ReconciliationIssueCode):
            raise FiscalValidationError("code must be ReconciliationIssueCode")
        object.__setattr__(self, "message", _required(self.message, "message", 500))
        if self.document_id is not None:
            object.__setattr__(
                self,
                "document_id",
                _required(self.document_id, "document_id", 128),
            )


@dataclass(frozen=True, slots=True)
class FiscalReconciliationResult:
    status: ReconciliationStatus
    scope: ExecutionScope
    source: SourceReference
    fingerprint: str
    selected_document_id: str | None
    issues: tuple[ReconciliationIssue, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReconciliationStatus):
            raise FiscalValidationError("status must be ReconciliationStatus")
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.source, SourceReference):
            raise FiscalValidationError("source must be SourceReference")
        normalized = self.fingerprint.strip().lower()
        if len(normalized) != 64:
            raise FiscalValidationError("fingerprint must be SHA-256 hex")
        try:
            int(normalized, 16)
        except ValueError as exc:
            raise FiscalValidationError("fingerprint must be hexadecimal") from exc
        object.__setattr__(self, "fingerprint", normalized)
        if self.selected_document_id is not None:
            object.__setattr__(
                self,
                "selected_document_id",
                _required(self.selected_document_id, "selected_document_id", 128),
            )
        if not all(isinstance(issue, ReconciliationIssue) for issue in self.issues):
            raise FiscalValidationError("issues must contain ReconciliationIssue values")
        if self.status is ReconciliationStatus.MATCHED and self.issues:
            raise FiscalValidationError("matched reconciliation cannot contain issues")


class FiscalReconciliationEngine:
    """Pure reconciliation service; it performs no provider or host mutation."""

    def reconcile(
        self,
        host: HostSettlementSnapshot,
        candidates: tuple[FiscalReconciliationCandidate, ...],
    ) -> FiscalReconciliationResult:
        if not isinstance(host, HostSettlementSnapshot):
            raise FiscalValidationError("host must be HostSettlementSnapshot")
        if not isinstance(candidates, tuple) or not all(
            isinstance(candidate, FiscalReconciliationCandidate) for candidate in candidates
        ):
            raise FiscalValidationError(
                "candidates must be a tuple of FiscalReconciliationCandidate"
            )

        self._validate_identity(host, candidates)
        fingerprint = self._fingerprint(host, candidates)
        issues: list[ReconciliationIssue] = []

        if host.settled_payment_amount.amount != host.sale_amount.amount:
            issues.append(
                ReconciliationIssue(
                    code=ReconciliationIssueCode.HOST_PAYMENT_MISMATCH,
                    message="host payment less change does not equal settled sale amount",
                )
            )

        authorized = tuple(
            candidate
            for candidate in candidates
            if candidate.state is FiscalDocumentState.AUTHORIZED
        )
        pending = tuple(candidate for candidate in candidates if candidate.state in _PENDING_STATES)
        cancelled = tuple(
            candidate
            for candidate in candidates
            if candidate.state is FiscalDocumentState.CANCELLED
        )

        if len(authorized) > 1:
            issues.append(
                ReconciliationIssue(
                    code=ReconciliationIssueCode.DUPLICATE_AUTHORIZED_FISCAL_DOCUMENT,
                    message="more than one authorized fiscal document exists for the sale",
                )
            )
            return self._result(
                host,
                fingerprint,
                ReconciliationStatus.DIVERGENT,
                None,
                issues,
            )

        if len(authorized) == 1:
            selected = authorized[0]
            if pending:
                issues.append(
                    ReconciliationIssue(
                        code=ReconciliationIssueCode.PARALLEL_FISCAL_ATTEMPT,
                        message="authorized document coexists with a non-final fiscal attempt",
                        document_id=selected.document_id,
                    )
                )
            self._compare_amounts(host, selected, issues)
            status = (
                ReconciliationStatus.DIVERGENT if issues else ReconciliationStatus.MATCHED
            )
            return self._result(
                host,
                fingerprint,
                status,
                selected.document_id,
                issues,
            )

        if pending and not issues:
            issues.append(
                ReconciliationIssue(
                    code=ReconciliationIssueCode.FISCAL_PROCESSING_PENDING,
                    message="fiscal processing has not reached an authorized terminal state",
                )
            )
            return self._result(
                host,
                fingerprint,
                ReconciliationStatus.PENDING,
                None,
                issues,
            )

        if cancelled:
            issues.append(
                ReconciliationIssue(
                    code=ReconciliationIssueCode.CLOSED_SALE_WITH_CANCELLED_FISCAL,
                    message="settled sale has only cancelled fiscal document evidence",
                )
            )
        else:
            issues.append(
                ReconciliationIssue(
                    code=ReconciliationIssueCode.MISSING_AUTHORIZED_FISCAL_DOCUMENT,
                    message="settled sale has no authorized fiscal document",
                )
            )
        return self._result(
            host,
            fingerprint,
            ReconciliationStatus.DIVERGENT,
            None,
            issues,
        )

    @staticmethod
    def _validate_identity(
        host: HostSettlementSnapshot,
        candidates: tuple[FiscalReconciliationCandidate, ...],
    ) -> None:
        document_ids: set[str] = set()
        for candidate in candidates:
            if candidate.scope.partition_key != host.scope.partition_key:
                raise ReconciliationContractError(
                    "fiscal candidate crosses host tenant/unit/environment scope"
                )
            if candidate.source.canonical_tuple != host.source.canonical_tuple:
                raise ReconciliationContractError(
                    "fiscal candidate does not reference the reconciled host sale"
                )
            if candidate.document_id in document_ids:
                raise ReconciliationContractError("duplicate candidate document_id in input")
            document_ids.add(candidate.document_id)

    @staticmethod
    def _compare_amounts(
        host: HostSettlementSnapshot,
        fiscal: FiscalReconciliationCandidate,
        issues: list[ReconciliationIssue],
    ) -> None:
        if fiscal.net_amount.amount != host.sale_amount.amount:
            issues.append(
                ReconciliationIssue(
                    code=ReconciliationIssueCode.SALE_FISCAL_TOTAL_MISMATCH,
                    message="authorized fiscal net amount differs from settled sale amount",
                    document_id=fiscal.document_id,
                )
            )
        if fiscal.settled_payment_amount.amount != fiscal.net_amount.amount:
            issues.append(
                ReconciliationIssue(
                    code=ReconciliationIssueCode.FISCAL_PAYMENT_MISMATCH,
                    message="fiscal payment less change differs from fiscal net amount",
                    document_id=fiscal.document_id,
                )
            )
        if (
            fiscal.payment_amount.amount != host.payment_amount.amount
            or fiscal.change_amount.amount != host.change_amount.amount
        ):
            issues.append(
                ReconciliationIssue(
                    code=ReconciliationIssueCode.PAYMENT_SNAPSHOT_MISMATCH,
                    message="fiscal payment/change snapshot differs from host settlement",
                    document_id=fiscal.document_id,
                )
            )

    @staticmethod
    def _fingerprint(
        host: HostSettlementSnapshot,
        candidates: tuple[FiscalReconciliationCandidate, ...],
    ) -> str:
        material = {
            "tenant_id": host.scope.tenant_id,
            "unit_id": host.scope.unit_id,
            "environment": host.scope.environment.value,
            "source": host.source.canonical_tuple,
            "sale_amount": str(host.sale_amount.amount),
            "payment_amount": str(host.payment_amount.amount),
            "change_amount": str(host.change_amount.amount),
            "settled_at": host.settled_at.isoformat(),
            "candidates": [
                {
                    "document_id": candidate.document_id,
                    "state": candidate.state.value,
                    "net_amount": str(candidate.net_amount.amount),
                    "payment_amount": str(candidate.payment_amount.amount),
                    "change_amount": str(candidate.change_amount.amount),
                }
                for candidate in sorted(candidates, key=lambda item: item.document_id)
            ],
        }
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _result(
        host: HostSettlementSnapshot,
        fingerprint: str,
        status: ReconciliationStatus,
        selected_document_id: str | None,
        issues: list[ReconciliationIssue],
    ) -> FiscalReconciliationResult:
        return FiscalReconciliationResult(
            status=status,
            scope=host.scope,
            source=host.source,
            fingerprint=fingerprint,
            selected_document_id=selected_document_id,
            issues=tuple(issues),
        )
