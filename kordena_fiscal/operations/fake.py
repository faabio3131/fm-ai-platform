"""Deterministic in-memory adapter for fiscal operations contract tests."""

from __future__ import annotations

from dataclasses import replace
from threading import Lock

from kordena_fiscal.gateway import GatewayProviderMetadata

from .events import (
    CancellationRequest,
    CancellationResult,
    FiscalEventStatus,
    FiscalOperationsGateway,
    FiscalQueryRequest,
    FiscalQueryResult,
    FiscalQueryStatus,
    InutilizationRequest,
    InutilizationResult,
)


class FakeFiscalOperationsGateway(FiscalOperationsGateway):
    """Synthetic, thread-safe adapter with no network or secret material."""

    def __init__(
        self,
        *,
        query_status: FiscalQueryStatus = FiscalQueryStatus.AUTHORIZED,
        event_status: FiscalEventStatus = FiscalEventStatus.ACCEPTED,
    ) -> None:
        self.query_status = query_status
        self.event_status = event_status
        self._provider = GatewayProviderMetadata("synthetic-operations", "v1")
        self._lock = Lock()
        self._query_calls: list[FiscalQueryRequest] = []
        self._cancel_calls: list[CancellationRequest] = []
        self._inutilization_calls: list[InutilizationRequest] = []

    @property
    def query_calls(self) -> tuple[FiscalQueryRequest, ...]:
        with self._lock:
            return tuple(self._query_calls)

    @property
    def cancel_calls(self) -> tuple[CancellationRequest, ...]:
        with self._lock:
            return tuple(self._cancel_calls)

    @property
    def inutilization_calls(self) -> tuple[InutilizationRequest, ...]:
        with self._lock:
            return tuple(self._inutilization_calls)

    def query(self, request: FiscalQueryRequest) -> FiscalQueryResult:
        with self._lock:
            self._query_calls.append(request)
        protocol = (
            "SYNTHETIC-AUTH-PROTOCOL"
            if self.query_status is FiscalQueryStatus.AUTHORIZED
            else None
        )
        return FiscalQueryResult(
            status=self.query_status,
            scope=request.scope,
            access_key=request.access_key,
            provider=self._provider,
            provider_request_id=f"query-{len(self.query_calls)}",
            protocol_reference=protocol,
        )

    def cancel(self, request: CancellationRequest) -> CancellationResult:
        with self._lock:
            self._cancel_calls.append(request)
        common = {
            "scope": request.scope,
            "access_key": request.access_key,
            "request_id": request.request_id,
            "provider": self._provider,
            "provider_request_id": f"cancel-{len(self.cancel_calls)}",
        }
        if self.event_status is FiscalEventStatus.ACCEPTED:
            return CancellationResult(
                status=self.event_status,
                event_protocol_reference="SYNTHETIC-CANCEL-PROTOCOL",
                **common,  # type: ignore[arg-type]
            )
        if self.event_status is FiscalEventStatus.REJECTED:
            return CancellationResult(
                status=self.event_status,
                rejection_code="SYNTHETIC-REJECTION",
                rejection_message="synthetic cancellation rejection",
                **common,  # type: ignore[arg-type]
            )
        return CancellationResult(
            status=self.event_status,
            **common,  # type: ignore[arg-type]
        )

    def inutilize(self, request: InutilizationRequest) -> InutilizationResult:
        with self._lock:
            self._inutilization_calls.append(request)
        common = {
            "scope": request.scope,
            "model": request.model,
            "series": request.series,
            "first_number": request.first_number,
            "last_number": request.last_number,
            "request_id": request.request_id,
            "provider": self._provider,
            "provider_request_id": f"inutilize-{len(self.inutilization_calls)}",
        }
        if self.event_status is FiscalEventStatus.ACCEPTED:
            return InutilizationResult(
                status=self.event_status,
                event_protocol_reference="SYNTHETIC-INUTILIZATION-PROTOCOL",
                **common,  # type: ignore[arg-type]
            )
        if self.event_status is FiscalEventStatus.REJECTED:
            return InutilizationResult(
                status=self.event_status,
                rejection_code="SYNTHETIC-REJECTION",
                rejection_message="synthetic inutilization rejection",
                **common,  # type: ignore[arg-type]
            )
        return InutilizationResult(
            status=self.event_status,
            **common,  # type: ignore[arg-type]
        )


class MutatingFiscalOperationsGateway(FakeFiscalOperationsGateway):
    """Test helper that deliberately violates echoed request identity."""

    def __init__(self, *, mutate: str) -> None:
        super().__init__()
        self._mutate = mutate

    def cancel(self, request: CancellationRequest) -> CancellationResult:
        result = super().cancel(request)
        if self._mutate == "cancel_request_id":
            return replace(result, request_id="f" * 64)
        if self._mutate == "cancel_scope":
            other_scope = replace(request.scope, unit_id="other-unit")
            return replace(result, scope=other_scope)
        return result

    def inutilize(self, request: InutilizationRequest) -> InutilizationResult:
        result = super().inutilize(request)
        if self._mutate == "inutilization_range":
            return replace(result, last_number=request.last_number + 1)
        return result
