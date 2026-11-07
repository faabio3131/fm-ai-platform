"""NFCore S2S issuance maps Kordena immutable venda.criada outbox without fake notes."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from infra.fiscal.nfcore_bridge_runtime import NfcoreFiscalOperationsGateway
from infra.fiscal.nfcore_issuance_contract import (
    NfcoreFiscalPayloadInvalid,
    to_nfcore_issuance,
)
from infra.fiscal.runtime_adapters import FiscalRuntimeConfigurationError
from kordena_fiscal.contingency import InMemoryFiscalOutboxStore
from tests.integration.fiscal.test_wp031c_outbound_bridge import _bridge, _event
from tests.unit.orders.factories import pedido


class _Resolver:
    def configuration_for_scope(self, scope):
        from infra.fiscal.runtime_adapters import FiscalRuntimeConfiguration

        return FiscalRuntimeConfiguration(
            configuracao_id="nfcore-tenant-a",
            provider="nfcore",
            environment=scope.environment,
            public_parameters={"host_namespace": "fm.kordena"},
            credential_purposes={"bearer_token": "token", "workload_credential_id": "id"},
            homologated=False,
            homologation_evidence_reference=None,
        )

    def credential(self, *, scope, role):
        from core.seguranca.segredos import SecretValue
        from infra.fiscal.runtime_adapters import ResolvedFiscalCredential

        return ResolvedFiscalCredential(
            role=role,
            reference="vault:" + role,
            value=SecretValue("synthetic_" + role),
        )


def _entry():
    return _bridge(InMemoryFiscalOutboxStore()).process(
        event=_event(), pedido=pedido(),
    ).outbox.entry


def test_nfcore_issue_maps_authoritative_sale_without_duplicating_tax_calculation():
    entry = _entry()
    translated = to_nfcore_issuance(entry)
    assert translated["contract_version"] == "1.0.0"
    assert translated["document"]["kind"] == "nfce"
    assert translated["operation"]["operation_reference"] == {
        "type": "venda", "id": "sale-1",
    }
    assert translated["operation"]["totals"]["net_amount"]["amount"] == "24"
    assert translated["document"]["items"][0]["item_reference"] == {
        "type": "produto", "id": "produto-que-pode-mudar",
    }
    assert translated["document"]["items"][0]["quantity"] == "1"
    assert translated["operation"]["payments"][0]["method"] == "pix"


def test_nfcore_issue_calls_capability_then_official_endpoint_with_idempotency():
    calls = []

    def exchange(url, body, headers):
        calls.append((url, json.loads(body), dict(headers)))
        if url.endswith("/v1/capabilities/query"):
            return {
                "readiness": "HOMOLOGATION_READY",
                "capabilities": ["issue"],
                "correlation_id": "corr-fiscal",
            }
        assert url.endswith("/v1/issuances")
        return {
            "contract_version": "1.0.0",
            "status": "accepted",
            "request_id": "request-nfcore-test",
            "replay": False,
            "correlation_id": "corr-fiscal",
        }

    entry = _entry()
    gateway = NfcoreFiscalOperationsGateway(
        _Resolver(), exchange=exchange, base_url="https://nfcore.example.com"
    )
    result = gateway.issue_outbox_entry(entry)
    assert result["status"] == "accepted"
    assert [url.rsplit("/", 1)[-1] for url, _, _ in calls] == [
        "query", "issuances",
    ]
    assert calls[1][2]["Idempotency-Key"] == entry.deduplication_key
    assert calls[1][2]["X-FM-Unit-Id"] == "unidade-a"
    assert calls[1][1]["operation"]["operation_kind"] == "sale"


def test_nfcore_issue_stops_if_readiness_contract_only():
    calls = []

    def exchange(url, body, headers):
        calls.append(url)
        return {
            "readiness": "CONTRACT_ONLY",
            "capabilities": ["issue"],
            "correlation_id": "corr-fiscal",
        }

    gateway = NfcoreFiscalOperationsGateway(
        _Resolver(), exchange=exchange, base_url="https://nfcore.example.com"
    )
    with pytest.raises(FiscalRuntimeConfigurationError):
        gateway.issue_outbox_entry(_entry())
    assert len(calls) == 1
    assert calls[0].endswith("/v1/capabilities/query")


def test_nfcore_issue_refuses_mismatched_snapshot_scope_and_payment_amount():
    entry = _entry()
    payload = json.loads(entry.payload)
    payload["scope"]["unit_id"] = "unidade-invasora"
    poisoned = json.dumps(payload, sort_keys=True).encode()
    altered = replace(
        entry,
        payload=poisoned,
        payload_sha256=hashlib.sha256(poisoned).hexdigest(),
    )
    with pytest.raises(NfcoreFiscalPayloadInvalid, match="scope mismatch"):
        to_nfcore_issuance(altered)

    payload["scope"]["unit_id"] = "unidade-a"
    payload["totals"]["net_amount"]["amount"] = "999.00"
    poisoned = json.dumps(payload, sort_keys=True).encode()
    altered = replace(
        entry,
        payload=poisoned,
        payload_sha256=hashlib.sha256(poisoned).hexdigest(),
    )
    with pytest.raises(NfcoreFiscalPayloadInvalid, match="totals"):
        to_nfcore_issuance(altered)
