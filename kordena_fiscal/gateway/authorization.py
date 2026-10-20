"""Provider-neutral authorization gateway contracts and boundary validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from kordena_fiscal.domain import ExecutionScope, FiscalDomainError, FiscalValidationError
from kordena_fiscal.lifecycle import IdempotencyKey
from kordena_fiscal.xml import NfeAccessKey


class GatewayContractError(FiscalDomainError):
    """Raised when a fiscal gateway adapter returns an inconsistent result."""


class AuthorizationStatus(StrEnum):
    AUTHORIZED = "authorized"
    REJECTED = "rejected"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class GatewayProviderMetadata:
    """Non-secret adapter identity recorded for observability/audit."""

    provider_name: str
    adapter_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_name",
            _required(self.provider_name, "provider_name", 128),
        )
        object.__setattr__(
            self,
            "adapter_version",
            _required(self.adapter_version, "adapter_version", 64),
        )


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    """Signed XML authorization request independent of transport/provider details."""

    scope: ExecutionScope
    access_key: NfeAccessKey
    signed_xml: bytes
    idempotency_key: IdempotencyKey
    request_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.access_key, NfeAccessKey):
            raise FiscalValidationError("access_key must be NfeAccessKey")
        if not isinstance(self.signed_xml, bytes) or not self.signed_xml:
            raise FiscalValidationError("signed_xml must be non-empty bytes")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise FiscalValidationError("idempotency_key must be IdempotencyKey")
        object.__setattr__(
            self,
            "request_fingerprint",
            _sha256_hex(self.request_fingerprint, "request_fingerprint"),
        )


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    """Normalized authorization outcome returned by any gateway adapter."""

    status: AuthorizationStatus
    scope: ExecutionScope
    access_key: NfeAccessKey
    idempotency_key: IdempotencyKey
    request_fingerprint: str
    provider: GatewayProviderMetadata
    provider_request_id: str | None = None
    protocol_reference: str | None = None
    rejection_code: str | None = None
    rejection_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, AuthorizationStatus):
            raise FiscalValidationError("status must be AuthorizationStatus")
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.access_key, NfeAccessKey):
            raise FiscalValidationError("access_key must be NfeAccessKey")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise FiscalValidationError("idempotency_key must be IdempotencyKey")
        object.__setattr__(
            self,
            "request_fingerprint",
            _sha256_hex(self.request_fingerprint, "request_fingerprint"),
        )
        if not isinstance(self.provider, GatewayProviderMetadata):
            raise FiscalValidationError("provider must be GatewayProviderMetadata")

        for field_name in (
            "provider_request_id",
            "protocol_reference",
            "rejection_code",
            "rejection_message",
        ):
            value = getattr(self, field_name)
            if value is not None:
                normalized = value.strip()
                if not normalized:
                    object.__setattr__(self, field_name, None)
                elif len(normalized) > 512:
                    raise FiscalValidationError(f"{field_name} exceeds max length 512")
                else:
                    object.__setattr__(self, field_name, normalized)

        if self.status is AuthorizationStatus.AUTHORIZED:
            if self.protocol_reference is None:
                raise FiscalValidationError(
                    "authorized result requires protocol_reference"
                )
            if self.rejection_code is not None or self.rejection_message is not None:
                raise FiscalValidationError(
                    "authorized result cannot contain rejection metadata"
                )
        elif self.status is AuthorizationStatus.REJECTED:
            if self.protocol_reference is not None:
                raise FiscalValidationError(
                    "rejected result cannot contain protocol_reference"
                )
            if self.rejection_code is None or self.rejection_message is None:
                raise FiscalValidationError(
                    "rejected result requires rejection_code and rejection_message"
                )
        else:
            if self.protocol_reference is not None:
                raise FiscalValidationError(
                    "pending result cannot contain protocol_reference"
                )
            if self.rejection_code is not None or self.rejection_message is not None:
                raise FiscalValidationError(
                    "pending result cannot contain rejection metadata"
                )


class FiscalGateway(Protocol):
    """Authorization adapter contract; credentials and transport remain private."""

    def authorize(self, request: AuthorizationRequest) -> AuthorizationResult: ...


class FiscalGatewayClient:
    """Fail-closed boundary around a provider-specific FiscalGateway adapter."""

    def __init__(self, gateway: FiscalGateway) -> None:
        self._gateway = gateway

    def authorize(self, request: AuthorizationRequest) -> AuthorizationResult:
        if not isinstance(request, AuthorizationRequest):
            raise FiscalValidationError("request must be AuthorizationRequest")
        result = self._gateway.authorize(request)
        self._validate_result(request, result)
        return result

    @staticmethod
    def _validate_result(
        request: AuthorizationRequest,
        result: AuthorizationResult,
    ) -> None:
        if not isinstance(result, AuthorizationResult):
            raise GatewayContractError("gateway must return AuthorizationResult")
        if result.scope != request.scope:
            raise GatewayContractError("gateway returned a different execution scope")
        if result.access_key != request.access_key:
            raise GatewayContractError("gateway returned a different access key")
        if result.idempotency_key != request.idempotency_key:
            raise GatewayContractError("gateway returned a different idempotency key")
        if result.request_fingerprint != request.request_fingerprint:
            raise GatewayContractError("gateway returned a different request fingerprint")


def _required(value: str, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise FiscalValidationError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise FiscalValidationError(f"{field_name} exceeds max length {max_length}")
    return normalized


def _sha256_hex(value: str, field_name: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise FiscalValidationError(f"{field_name} must be SHA-256 hex")
    try:
        int(normalized, 16)
    except ValueError as exc:
        raise FiscalValidationError(f"{field_name} must be hexadecimal") from exc
    return normalized
