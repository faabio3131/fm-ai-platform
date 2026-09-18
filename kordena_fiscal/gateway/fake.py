"""Deterministic fake gateway used for contract tests and technical orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import Lock

from kordena_fiscal.domain import FiscalValidationError

from .authorization import (
    AuthorizationRequest,
    AuthorizationResult,
    AuthorizationStatus,
    GatewayProviderMetadata,
)


class FakeGatewayMode(StrEnum):
    AUTHORIZE = "authorize"
    REJECT = "reject"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class _FakeGatewayConfig:
    mode: FakeGatewayMode
    protocol_reference: str = "SYNTHETIC-PROTOCOL-1"
    rejection_code: str = "SYNTHETIC-REJECTION"
    rejection_message: str = "synthetic rejection for contract test"


class FakeFiscalGateway:
    """Thread-safe deterministic adapter; never performs network I/O."""

    def __init__(
        self,
        mode: FakeGatewayMode = FakeGatewayMode.AUTHORIZE,
        *,
        provider_name: str = "synthetic-fiscal-gateway",
        adapter_version: str = "test-v1",
    ) -> None:
        if not isinstance(mode, FakeGatewayMode):
            raise FiscalValidationError("mode must be FakeGatewayMode")
        self._config = _FakeGatewayConfig(mode=mode)
        self._provider = GatewayProviderMetadata(provider_name, adapter_version)
        self._lock = Lock()
        self._calls: list[AuthorizationRequest] = []

    @property
    def calls(self) -> tuple[AuthorizationRequest, ...]:
        with self._lock:
            return tuple(self._calls)

    def authorize(self, request: AuthorizationRequest) -> AuthorizationResult:
        if not isinstance(request, AuthorizationRequest):
            raise FiscalValidationError("request must be AuthorizationRequest")
        with self._lock:
            self._calls.append(request)
            call_number = len(self._calls)

        provider_request_id = f"fake-request-{call_number}"
        if self._config.mode is FakeGatewayMode.AUTHORIZE:
            return AuthorizationResult(
                status=AuthorizationStatus.AUTHORIZED,
                scope=request.scope,
                access_key=request.access_key,
                idempotency_key=request.idempotency_key,
                request_fingerprint=request.request_fingerprint,
                provider=self._provider,
                provider_request_id=provider_request_id,
                protocol_reference=self._config.protocol_reference,
            )
        if self._config.mode is FakeGatewayMode.REJECT:
            return AuthorizationResult(
                status=AuthorizationStatus.REJECTED,
                scope=request.scope,
                access_key=request.access_key,
                idempotency_key=request.idempotency_key,
                request_fingerprint=request.request_fingerprint,
                provider=self._provider,
                provider_request_id=provider_request_id,
                rejection_code=self._config.rejection_code,
                rejection_message=self._config.rejection_message,
            )
        return AuthorizationResult(
            status=AuthorizationStatus.PENDING,
            scope=request.scope,
            access_key=request.access_key,
            idempotency_key=request.idempotency_key,
            request_fingerprint=request.request_fingerprint,
            provider=self._provider,
            provider_request_id=provider_request_id,
        )
