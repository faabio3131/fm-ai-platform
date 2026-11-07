"""NFCore Bridge: no fiscal authority duplicated, no secret leakage or fake approval."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.seguranca.segredos import SecretValue
from infra.fiscal.nfcore_bridge_runtime import (
    NfcoreBridgeContractError,
    NfcoreFiscalOperationsGateway,
    _bridge_base_url,
)
from infra.fiscal.runtime_adapters import (
    FiscalRuntimeConfiguration,
    FiscalRuntimeConfigurationError,
    ResolvedFiscalCredential,
)
from kordena_fiscal.domain import (
    Cnpj,
    ElectronicInvoiceModel,
    ExecutionScope,
    FiscalEnvironment,
)
from kordena_fiscal.operations import (
    CancellationRequest,
    FiscalEventStatus,
    InutilizationRequest,
)
from kordena_fiscal.xml import AccessKeyInput, build_access_key


class ResolverFake:
    def __init__(
        self, *, homologated=True, provider="nfcore", namespace="fm.kordena"
    ):
        self.config = FiscalRuntimeConfiguration(
            configuracao_id="nfcore-test",
            provider=provider,
            environment=FiscalEnvironment.HOMOLOGATION,
            public_parameters={"host_namespace": namespace},
            credential_purposes={"bearer_token": "auth", "workload_credential_id": "id"},
            homologated=homologated,
            homologation_evidence_reference="homolog-test" if homologated else None,
        )

    def configuration_for_scope(self, scope):
        assert scope.tenant_id == "tenant-a" and scope.unit_id == "unit-a"
        return self.config

    def credential(self, *, scope, role):
        assert scope.unit_id == "unit-a"
        return ResolvedFiscalCredential(
            role=role,
            reference="vault:synthetic-" + role,
            value=SecretValue("synthetic-secret" if role == "bearer_token" else "id-test"),
        )


def _scope(env=FiscalEnvironment.HOMOLOGATION):
    return ExecutionScope("tenant-a", "unit-a", env, "corr-nfcore-test")


def _key():
    return build_access_key(
        AccessKeyInput(
            state_ibge_code="35",
            issued_at=datetime(2026, 11, 7, 12, tzinfo=timezone.utc),
            issuer_cnpj=Cnpj("11222333000181"),
            model=ElectronicInvoiceModel.NFCE,
            series=1,
            invoice_number=123,
            emission_type=1,
            numeric_code=12345678,
        )
    )


def _cancel():
    return CancellationRequest.build(
        scope=_scope(),
        access_key=_key(),
        authorization_protocol="nprot-123",
        justification="Cancelamento autorizado para teste",
    )


def _exchange(*, readiness="HOMOLOGATION_READY", allowed=("cancel",), wrong_scope=False):
    captured = []

    def send(url, body, headers):
        payload = json.loads(body)
        captured.append((url, payload, dict(headers)))
        corr = "corr-outro" if wrong_scope else headers["X-Correlation-Id"]
        if url.endswith("/v1/capabilities/query"):
            return {
                "contract_version": "1.0.0",
                "readiness": readiness,
                "capability_version": "v1",
                "capabilities": list(allowed),
                "correlation_id": corr,
            }
        if url.endswith("/v1/cancellations"):
            return {
                "status": "accepted",
                "request_id": "remote-event-123",
                "access_key": payload["access_key"],
                "event_protocol_reference": "protocol-cancel-123",
                "correlation_id": corr,
            }
        if url.endswith("/v1/inutilizations"):
            return {
                "status": "accepted",
                "request_id": "remote-range-123",
                "event_protocol_reference": "protocol-range-123",
                "model": payload["model"],
                "series": payload["series"],
                "first_number": payload["first_number"],
                "last_number": payload["last_number"],
                "correlation_id": corr,
            }
        raise AssertionError("unexpected provider endpoint")

    return captured, send


def test_cancellation_checks_capability_before_mutation_and_binds_scope():
    calls, exchange = _exchange()
    gateway = NfcoreFiscalOperationsGateway(
        ResolverFake(), exchange=exchange, base_url="https://nfcore.example.com"
    )
    request = _cancel()
    result = gateway.cancel(request)
    assert result.status is FiscalEventStatus.ACCEPTED
    assert result.request_id == request.request_id
    assert result.provider_request_id == "remote-event-123"
    assert result.event_protocol_reference == "protocol-cancel-123"
    assert [url.rsplit("/", 1)[-1] for url, _, _ in calls] == [
        "query", "cancellations"
    ]
    _, body, headers = calls[1]
    assert body["access_key"] == request.access_key.value
    assert headers["X-FM-Host-Namespace"] == "fm.kordena"
    assert headers["X-FM-Tenant-Id"] == "tenant-a"
    assert headers["X-FM-Unit-Id"] == "unit-a"
    assert headers["Idempotency-Key"] == request.request_id
    assert headers["Authorization"] == "Bearer synthetic-secret"
    assert "synthetic-secret" not in repr(result)


def test_contract_only_or_missing_capability_never_sends_fiscal_mutation():
    for readiness, capabilities in [
        ("CONTRACT_ONLY", ("cancel",)),
        ("HOMOLOGATION_READY", ("query",)),
    ]:
        calls, exchange = _exchange(readiness=readiness, allowed=capabilities)
        gateway = NfcoreFiscalOperationsGateway(
            ResolverFake(), exchange=exchange, base_url="https://nfcore.example.com"
        )
        with pytest.raises(FiscalRuntimeConfigurationError):
            gateway.cancel(_cancel())
        assert len(calls) == 1


def test_production_requires_explicit_evidence_and_core_approval():
    calls, exchange = _exchange(
        readiness="HOMOLOGATION_READY", allowed=("inutilize",)
    )
    gateway = NfcoreFiscalOperationsGateway(
        ResolverFake(), exchange=exchange, base_url="https://nfcore.example.com"
    )
    request = InutilizationRequest.build(
        scope=_scope(FiscalEnvironment.PRODUCTION),
        model=ElectronicInvoiceModel.NFCE,
        series=1,
        first_number=10,
        last_number=12,
        justification="Inutilização por falha controlada",
    )
    with pytest.raises(FiscalRuntimeConfigurationError):
        gateway.inutilize(request)
    assert len(calls) == 1


def test_mismatched_correlation_is_rejected_before_mutation():
    calls, exchange = _exchange(wrong_scope=True)
    gateway = NfcoreFiscalOperationsGateway(
        ResolverFake(), exchange=exchange, base_url="https://nfcore.example.com"
    )
    with pytest.raises(NfcoreBridgeContractError):
        gateway.cancel(_cancel())
    assert len(calls) == 1


def test_unexpected_provider_is_rejected_before_network_call():
    calls, exchange = _exchange()
    gateway = NfcoreFiscalOperationsGateway(
        ResolverFake(provider="sefaz"), exchange=exchange,
        base_url="https://nfcore.example.com",
    )
    with pytest.raises(FiscalRuntimeConfigurationError):
        gateway.cancel(_cancel())
    assert not calls


def test_bridge_url_is_HTTPS_only_and_does_not_accept_path_or_userinfo(monkeypatch):
    for url in ("", "http://example.com", "https://user:pw@example.com",
                "https://example.com/api", "https://example.com?x=1"):
        monkeypatch.setenv("FM_AI_NFCORE_BRIDGE_BASE_URL", url)
        with pytest.raises(FiscalRuntimeConfigurationError):
            _bridge_base_url()
    monkeypatch.setenv("FM_AI_NFCORE_BRIDGE_BASE_URL", "https://nfcore.example.com/")
    assert _bridge_base_url() == "https://nfcore.example.com"
