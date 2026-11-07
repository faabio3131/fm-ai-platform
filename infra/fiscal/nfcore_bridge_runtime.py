"""NFCore S2S Bridge adapter for Kordena Fiscal V1 operations.

Only NFCore is fiscal authority. This module does not sign XML, issue a fiscal
document, infer jurisdiction readiness or invent SEFAZ authorization.
Contract: faabio3131/nf-core-v001/contracts/v1/openapi.json (2026-11-07).
"""
from __future__ import annotations

import json
import os
import ssl
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from sqlalchemy.orm import Session

from infra.fiscal.runtime_adapters import (
    FiscalControlPlaneResolver,
    FiscalRuntimeConfigurationError,
    FiscalProviderUnavailableError,
)
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from kordena_fiscal.domain import ExecutionScope, FiscalEnvironment
from kordena_fiscal.gateway import GatewayProviderMetadata
from kordena_fiscal.operations import (
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

HOST_NAMESPACE = "fm.kordena"
PROVIDER = GatewayProviderMetadata(provider_name="nfcore", adapter_version="bridge-v1")
MAX_RESPONSE = 262_144
Exchange = Callable[[str, bytes, Mapping[str, str]], dict[str, Any]]


class NfcoreBridgeContractError(RuntimeError):
    """Unexpected, incomplete or untrusted fiscal provider response."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _bridge_base_url() -> str:
    value = os.getenv("FM_AI_NFCORE_BRIDGE_BASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise FiscalRuntimeConfigurationError(
            "NFCore Bridge requires an explicit HTTPS origin"
        )
    return value


def _post_json(url: str, body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
    """HTTPS only, no redirects, no opaque retries and no secret-bearing errors."""
    request = Request(
        url, data=body, headers=dict(headers), method="POST"
    )
    opener = build_opener(
        HTTPSHandler(context=ssl.create_default_context()),
        _NoRedirects(),
    )
    try:
        with opener.open(request, timeout=12) as response:
            if response.status not in (200, 201, 202):
                raise FiscalProviderUnavailableError(
                    "NFCore Bridge did not accept the request"
                )
            response_bytes = response.read(MAX_RESPONSE + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise FiscalProviderUnavailableError(
            "NFCore Bridge unavailable; state requires reconciliation"
        ) from None
    if len(response_bytes) > MAX_RESPONSE:
        raise NfcoreBridgeContractError("NFCore response too large")
    try:
        payload = json.loads(response_bytes)
    except (ValueError, UnicodeError) as exc:
        raise NfcoreBridgeContractError("NFCore response is not valid JSON") from None
    if not isinstance(payload, dict):
        raise NfcoreBridgeContractError("NFCore response is not an object")
    return payload


def _require_text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise NfcoreBridgeContractError(f"NFCore response lacks {name}")
    return value.strip()


def _optional_text(payload: Mapping[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise NfcoreBridgeContractError(f"NFCore response invalid {name}")
    return value.strip()


class NfcoreFiscalOperationsGateway(FiscalOperationsGateway):
    """Scoped, readiness-gated delegate for query, cancel and inutilization."""

    def __init__(
        self,
        resolver: FiscalControlPlaneResolver,
        *,
        exchange: Exchange = _post_json,
        base_url: str | None = None,
    ) -> None:
        self._resolver = resolver
        self._exchange = exchange
        self._base_url = base_url

    def _origin(self) -> str:
        if self._base_url is not None:
            # Injecting an origin is only for an explicit test/composition.
            parsed = urlsplit(self._base_url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise FiscalRuntimeConfigurationError("invalid NFCore Bridge origin")
            return self._base_url.rstrip("/")
        return _bridge_base_url()

    def _call(
        self,
        *,
        scope: ExecutionScope,
        path: str,
        payload: Mapping[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        config = self._resolver.configuration_for_scope(scope)
        if config.provider != "nfcore":
            raise FiscalRuntimeConfigurationError(
                "NFCore Bridge requires a dedicated scoped provider configuration"
            )
        if config.public_parameters.get("host_namespace") != HOST_NAMESPACE:
            raise FiscalRuntimeConfigurationError("unexpected NFCore host namespace")
        if scope.environment is FiscalEnvironment.PRODUCTION and (
            not config.homologated
            or not config.homologation_evidence_reference
        ):
            raise FiscalRuntimeConfigurationError(
                "NFCore production requires provider homologation evidence"
            )

        token = self._resolver.credential(scope=scope, role="bearer_token")
        credential = self._resolver.credential(
            scope=scope, role="workload_credential_id"
        )
        if token is None or credential is None:
            raise FiscalRuntimeConfigurationError("NFCore workload not configured")
        headers = {
            "Authorization": "Bearer " + token.value.reveal(),
            "X-FM-Workload-Credential-Id": credential.value.reveal(),
            "X-FM-Host-Namespace": HOST_NAMESPACE,
            "X-FM-Tenant-Id": scope.tenant_id,
            "X-FM-Unit-Id": scope.unit_id,
            "X-FM-Environment": scope.environment.value,
            "X-Correlation-Id": scope.correlation_id,
            "Content-Type": "application/json",
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        body = json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        data = self._exchange(self._origin() + path, body, headers)
        if not isinstance(data, dict):
            raise NfcoreBridgeContractError("NFCore returned invalid payload")
        if _require_text(data, "correlation_id") != scope.correlation_id:
            raise NfcoreBridgeContractError("NFCore correlation does not match request")
        return data

    def _capability(
        self, scope: ExecutionScope, capability: str, kind: str
    ) -> None:
        data = self._call(
            scope=scope,
            path="/v1/capabilities/query",
            payload={"document_kind": kind},
        )
        readiness = _require_text(data, "readiness")
        allowed = data.get("capabilities")
        if not isinstance(allowed, list) or capability not in allowed:
            raise FiscalRuntimeConfigurationError(
                "NFCore fiscal capability unavailable for this scope"
            )
        if scope.environment is FiscalEnvironment.PRODUCTION:
            if readiness != "PRODUCTION_APPROVED":
                raise FiscalRuntimeConfigurationError(
                    "NFCore has not approved production for this scope"
                )
        elif readiness not in ("HOMOLOGATION_READY", "PRODUCTION_APPROVED"):
            raise FiscalRuntimeConfigurationError(
                "NFCore has not approved fiscal homologation for this scope"
            )

    def query(self, request: FiscalQueryRequest) -> FiscalQueryResult:
        kind = "nfce" if request.access_key.model.value == 65 else "nfe"
        self._capability(request.scope, "query", kind)
        data = self._call(
            scope=request.scope,
            path="/v1/queries",
            payload={"access_key": request.access_key.value},
        )
        if _require_text(data, "access_key") != request.access_key.value:
            raise NfcoreBridgeContractError("NFCore query key mismatch")
        return FiscalQueryResult(
            status=FiscalQueryStatus(_require_text(data, "status")),
            scope=request.scope,
            access_key=request.access_key,
            provider=PROVIDER,
            protocol_reference=_optional_text(data, "protocol_reference"),
        )

    def cancel(self, request: CancellationRequest) -> CancellationResult:
        kind = "nfce" if request.access_key.model.value == 65 else "nfe"
        self._capability(request.scope, "cancel", kind)
        data = self._call(
            scope=request.scope,
            path="/v1/cancellations",
            payload={
                "access_key": request.access_key.value,
                "authorization_protocol": request.authorization_protocol,
                "justification": request.justification,
            },
            idempotency_key=request.request_id,
        )
        if _require_text(data, "access_key") != request.access_key.value:
            raise NfcoreBridgeContractError("NFCore cancellation key mismatch")
        return CancellationResult(
            status=FiscalEventStatus(_require_text(data, "status")),
            scope=request.scope,
            access_key=request.access_key,
            request_id=request.request_id,
            provider=PROVIDER,
            provider_request_id=_require_text(data, "request_id"),
            event_protocol_reference=_optional_text(data, "event_protocol_reference"),
            rejection_code=_optional_text(data, "rejection_code"),
            rejection_message=_optional_text(data, "rejection_message"),
        )

    def inutilize(self, request: InutilizationRequest) -> InutilizationResult:
        kind = "nfce" if request.model.value == 65 else "nfe"
        self._capability(request.scope, "inutilize", kind)
        data = self._call(
            scope=request.scope,
            path="/v1/inutilizations",
            payload={
                "model": request.model.value,
                "series": request.series,
                "first_number": request.first_number,
                "last_number": request.last_number,
                "justification": request.justification,
            },
            idempotency_key=request.request_id,
        )
        for name, expected in (
            ("model", request.model.value),
            ("series", request.series),
            ("first_number", request.first_number),
            ("last_number", request.last_number),
        ):
            if type(data.get(name)) is not int or data[name] != expected:
                raise NfcoreBridgeContractError("NFCore inutilization scope mismatch")
        return InutilizationResult(
            status=FiscalEventStatus(_require_text(data, "status")),
            scope=request.scope,
            model=request.model,
            series=request.series,
            first_number=request.first_number,
            last_number=request.last_number,
            request_id=request.request_id,
            provider=PROVIDER,
            provider_request_id=_require_text(data, "request_id"),
            event_protocol_reference=_optional_text(data, "event_protocol_reference"),
            rejection_code=_optional_text(data, "rejection_code"),
            rejection_message=_optional_text(data, "rejection_message"),
        )


def create_nfcore_fiscal_gateway(session: Session) -> NfcoreFiscalOperationsGateway:
    """Enabled explicitly by platform ops, with scoped DB/vault secret references."""
    vault = EncryptedSQLAlchemySecretStore(session)
    return NfcoreFiscalOperationsGateway(FiscalControlPlaneResolver(session, vault))
