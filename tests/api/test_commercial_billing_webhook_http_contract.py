from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.commercial_billing import BillingProviderAdapterRegistryV1
from core.comercial.billing import BillingCallContext, WebhookVerificationResult
from core.comercial.billing_config import (
    BillingConnectionTestStatus,
    BillingEnvironment,
    BillingProviderAccountStatus,
)
from core.comercial.billing_events import (
    BillingCanonicalEventType,
    NormalizedBillingEvent,
)
from core.seguranca.segredos import ReferenceSecretStore, SecretValue
from http_api.commercial_billing_webhooks import (
    build_commercial_billing_webhook_router,
)
from infra.comercial.billing_config_orm import FMBillingProviderAccountORM
from infra.comercial.billing_payload_crypto import BillingWebhookPayloadCipher
from migrations.runner import run_migrations


class _Provider:
    provider_code = "PROVIDER_HTTP_TEST"

    def verify_webhook(
        self,
        *,
        payload: bytes,
        headers,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> WebhookVerificationResult:
        data = json.loads(payload.decode("utf-8"))
        assert credential.reveal() == "fake-http-secret"
        return WebhookVerificationResult(
            valid=headers.get("x-provider-signature") == "valid",
            event_id=str(data["id"]),
            event_type="payment",
        )

    def normalize_webhook(
        self,
        *,
        payload: bytes,
        verification: WebhookVerificationResult,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> NormalizedBillingEvent:
        data = json.loads(payload.decode("utf-8"))
        return NormalizedBillingEvent(
            provider_code=self.provider_code,
            external_event_id=verification.event_id or str(data["id"]),
            canonical_event_type=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
            occurred_at=datetime.fromisoformat(str(data["occurred_at"])),
            provider_sequence=1,
            external_transaction_ref=str(data["transaction_ref"]),
            amount=Decimal("25.00"),
            currency="BRL",
        )


def _client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        session.add(
            FMBillingProviderAccountORM(
                provider_account_id="provider-http-account",
                provider_code="PROVIDER_HTTP_TEST",
                display_name="HTTP provider",
                legal_entity_ref=None,
                environment=BillingEnvironment.SANDBOX.value,
                status=BillingProviderAccountStatus.ACTIVE.value,
                credential_secret_reference="mapping:http_secret",
                supported_payment_methods=["pix"],
                supports_recurring=True,
                supports_webhooks=True,
                priority=1,
                last_tested_at=datetime.now(timezone.utc),
                last_test_status=BillingConnectionTestStatus.PASS.value,
                correlation_id="corr-http",
                created_by="test",
                updated_by="test",
                version=1,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    api = FastAPI()
    api.include_router(
        build_commercial_billing_webhook_router(
            session_factory=factory,
            adapter_registry=BillingProviderAdapterRegistryV1((_Provider(),)),
            fallback_secret_store=ReferenceSecretStore(
                mapping={"http_secret": "fake-http-secret"}
            ),
            payload_cipher=BillingWebhookPayloadCipher(
                master_key=Fernet.generate_key().decode("ascii")
            ),
        )
    )
    return TestClient(api)


def _payload(event_id: str, transaction_ref: str) -> dict[str, str]:
    return {
        "id": event_id,
        "transaction_ref": transaction_ref,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }


def test_valid_webhook_is_accepted_without_echoing_payload_or_secret() -> None:
    client = _client()
    response = client.post(
        "/v1/commercial/billing/webhooks/provider-http-account",
        headers={"x-provider-signature": "valid"},
        json=_payload("evt-http-ok", "tx-http-ok"),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    assert body["status"] == "processed"
    assert body["event_id"] == "evt-http-ok"
    assert "fake-http-secret" not in response.text
    assert "transaction_ref" not in response.text


def test_forged_signature_is_rejected() -> None:
    client = _client()
    response = client.post(
        "/v1/commercial/billing/webhooks/provider-http-account",
        headers={"x-provider-signature": "forged"},
        json=_payload("evt-http-forged", "tx-http-forged"),
    )
    assert response.status_code == 401
    assert response.json()["accepted"] is False
    assert response.json()["status"] == "rejected"


def test_unknown_provider_account_fails_closed() -> None:
    client = _client()
    response = client.post(
        "/v1/commercial/billing/webhooks/missing-provider",
        headers={"x-provider-signature": "valid"},
        json=_payload("evt-http-missing", "tx-http-missing"),
    )
    assert response.status_code == 404
    assert response.json()["accepted"] is False
