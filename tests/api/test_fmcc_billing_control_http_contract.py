from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.commercial_billing import BillingProviderAdapterRegistryV1
from core.comercial.billing import BillingConnectionTestResult
from core.seguranca.segredos import ReferenceSecretStore, SecretValue
from http_api.fmcc_billing_control import build_fmcc_billing_control_router
from infra.comercial.billing_config_orm import FMBillingProviderAccountORM
from infra.seguranca.segredos_orm import SegredoIntegracaoORM
from migrations.runner import run_migrations

TOKEN = "fmcc-billing-control-token-0123456789abcdef"


class FakeBillingProvider:
    provider_code = "PROVIDER_TEST"

    def __init__(self) -> None:
        self.seen_credentials: list[str] = []

    def test_connection(
        self,
        *,
        context,
        credential: SecretValue,
    ) -> BillingConnectionTestResult:
        assert context.correlation_id
        self.seen_credentials.append(credential.reveal())
        return BillingConnectionTestResult(
            ok=True,
            provider_code=self.provider_code,
            detail_code="connection_ok",
        )


def _client(monkeypatch) -> tuple[TestClient, sessionmaker, FakeBillingProvider]:
    monkeypatch.setenv(
        "FM_AI_SECRET_MASTER_KEY",
        Fernet.generate_key().decode("ascii"),
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    provider = FakeBillingProvider()

    app = FastAPI()
    app.include_router(
        build_fmcc_billing_control_router(
            session_factory=factory,
            control_plane_token=TOKEN,
            adapter_registry=BillingProviderAdapterRegistryV1((provider,)),
            secret_store=ReferenceSecretStore(),
        )
    )
    return TestClient(app), factory, provider


def _actor(*, age: timedelta = timedelta()) -> dict[str, str]:
    return {
        "user_id": "fm-command-owner",
        "role": "owner",
        "step_up_at": (datetime.now(timezone.utc) - age).isoformat(),
    }


def _headers(*, idempotency_key: str | None = None) -> dict[str, str]:
    result = {
        "Authorization": f"Bearer {TOKEN}",
        "X-Correlation-ID": "command-billing-test",
    }
    if idempotency_key:
        result["Idempotency-Key"] = idempotency_key
    return result


def _create_body(*, holder_type: str, holder_ref: str) -> dict:
    return {
        "actor": _actor(),
        "provider_code": "PROVIDER_TEST",
        "display_name": "Conta Recebedora FM",
        "legal_entity_type": holder_type,
        "legal_entity_ref": holder_ref,
        "environment": "production",
        "supported_payment_methods": ["pix", "card"],
        "supports_recurring": True,
        "supports_webhooks": True,
        "priority": 10,
    }


def test_command_billing_configuration_options_are_provider_driven(
    monkeypatch,
) -> None:
    client, _factory, _provider = _client(monkeypatch)

    response = client.get(
        "/v1/control-plane/fmcc/billing/configuration-options",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.json()["provider_codes"] == ["PROVIDER_TEST"]
    assert response.json()["legal_entity_types"] == [
        {"value": "individual", "label": "Pessoa Física"},
        {"value": "company", "label": "Pessoa Jurídica"},
    ]
    assert "pix" in response.json()["payment_methods"]
    assert "production" in response.json()["environments"]


def test_command_billing_requires_service_auth(monkeypatch) -> None:
    client, _factory, _provider = _client(monkeypatch)

    response = client.get("/v1/control-plane/fmcc/billing/provider-accounts")

    assert response.status_code == 401


def test_command_billing_exposes_pf_and_pj_as_configurable_holder_types(
    monkeypatch,
) -> None:
    client, _factory, _provider = _client(monkeypatch)

    pf = client.post(
        "/v1/control-plane/fmcc/billing/provider-accounts",
        headers=_headers(idempotency_key="provider-pf"),
        json=_create_body(
            holder_type="individual",
            holder_ref="fm-owner-profile",
        ),
    )
    pj = client.post(
        "/v1/control-plane/fmcc/billing/provider-accounts",
        headers=_headers(idempotency_key="provider-pj"),
        json={
            **_create_body(
                holder_type="company",
                holder_ref="fm-company-profile",
            ),
            "display_name": "Conta Recebedora FM PJ",
            "priority": 20,
        },
    )

    assert pf.status_code == 201
    assert pf.json()["legal_entity_type"] == "individual"
    assert pf.json()["legal_entity_ref"] == "fm-owner-profile"
    assert pf.json()["credential_configured"] is False
    assert "credential_secret_reference" not in pf.json()

    assert pj.status_code == 201
    assert pj.json()["legal_entity_type"] == "company"
    assert pj.json()["legal_entity_ref"] == "fm-company-profile"
    assert pj.json()["credential_configured"] is False


def test_command_billing_requires_fresh_step_up_for_mutation(monkeypatch) -> None:
    client, _factory, _provider = _client(monkeypatch)
    body = _create_body(
        holder_type="individual",
        holder_ref="fm-owner-profile",
    )
    body["actor"] = _actor(age=timedelta(minutes=16))

    response = client.post(
        "/v1/control-plane/fmcc/billing/provider-accounts",
        headers=_headers(idempotency_key="stale-step-up"),
        json=body,
    )

    assert response.status_code == 403
    assert response.json()["error"] == "fmcc_control_plane.step_up_required"


def test_command_billing_stores_provider_credential_only_in_encrypted_vault(
    monkeypatch,
) -> None:
    client, factory, provider = _client(monkeypatch)
    raw_secret = '{"access_token":"fake-test","webhook_secret":"fake-webhook"}'

    created = client.post(
        "/v1/control-plane/fmcc/billing/provider-accounts",
        headers=_headers(idempotency_key="provider-vault"),
        json=_create_body(
            holder_type="individual",
            holder_ref="fm-owner-profile",
        ),
    )
    assert created.status_code == 201
    account = created.json()

    stored = client.post(
        (
            "/v1/control-plane/fmcc/billing/provider-accounts/"
            f"{account['provider_account_id']}/credential"
        ),
        headers=_headers(),
        json={
            "actor": _actor(),
            "expected_version": account["version"],
            "credential": raw_secret,
        },
    )
    assert stored.status_code == 200
    assert stored.json()["credential_configured"] is True
    assert raw_secret not in stored.text

    with factory() as session:
        provider_row = session.get(
            FMBillingProviderAccountORM,
            account["provider_account_id"],
        )
        assert provider_row is not None
        assert provider_row.credential_secret_reference is not None
        vault_row = session.get(
            SegredoIntegracaoORM,
            provider_row.credential_secret_reference,
        )
        assert vault_row is not None
        assert raw_secret not in vault_row.ciphertext

    tested = client.post(
        (
            "/v1/control-plane/fmcc/billing/provider-accounts/"
            f"{account['provider_account_id']}/test-connection"
        ),
        headers=_headers(),
        json={
            "actor": _actor(),
            "expected_version": stored.json()["version"],
            "timeout_seconds": 5,
        },
    )
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    assert provider.seen_credentials == [raw_secret]


def test_command_billing_can_activate_and_route_configured_product(
    monkeypatch,
) -> None:
    client, _factory, _provider = _client(monkeypatch)
    raw_secret = "credential-test-value"

    created = client.post(
        "/v1/control-plane/fmcc/billing/provider-accounts",
        headers=_headers(idempotency_key="provider-active"),
        json=_create_body(
            holder_type="company",
            holder_ref="fm-company-profile",
        ),
    ).json()

    stored = client.post(
        (
            "/v1/control-plane/fmcc/billing/provider-accounts/"
            f"{created['provider_account_id']}/credential"
        ),
        headers=_headers(),
        json={
            "actor": _actor(),
            "expected_version": created["version"],
            "credential": raw_secret,
        },
    ).json()

    tested = client.post(
        (
            "/v1/control-plane/fmcc/billing/provider-accounts/"
            f"{created['provider_account_id']}/test-connection"
        ),
        headers=_headers(),
        json={
            "actor": _actor(),
            "expected_version": stored["version"],
        },
    ).json()
    assert tested["ok"] is True

    activated = client.post(
        (
            "/v1/control-plane/fmcc/billing/provider-accounts/"
            f"{created['provider_account_id']}/status"
        ),
        headers=_headers(),
        json={
            "actor": _actor(),
            "expected_version": tested["account"]["version"],
            "status": "active",
        },
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"

    route = client.post(
        "/v1/control-plane/fmcc/billing/routing-policies",
        headers=_headers(idempotency_key="route-kordena-pix"),
        json={
            "actor": _actor(),
            "product_code": "KORDENA",
            "payment_method": "pix",
            "environment": "production",
            "requires_recurring": True,
            "requires_webhooks": True,
            "primary_provider_account_id": created["provider_account_id"],
            "fallback_provider_account_ids": [],
        },
    )

    assert route.status_code == 201
    assert route.json()["product_code"] == "KORDENA"
    assert (
        route.json()["primary_provider_account_id"]
        == created["provider_account_id"]
    )


def test_command_billing_production_activation_fails_without_pf_pj_profile(
    monkeypatch,
) -> None:
    client, _factory, _provider = _client(monkeypatch)
    body = _create_body(holder_type="individual", holder_ref="fm-owner-profile")
    body["legal_entity_type"] = None
    body["legal_entity_ref"] = None

    created = client.post(
        "/v1/control-plane/fmcc/billing/provider-accounts",
        headers=_headers(idempotency_key="provider-no-holder"),
        json=body,
    ).json()

    stored = client.post(
        (
            "/v1/control-plane/fmcc/billing/provider-accounts/"
            f"{created['provider_account_id']}/credential"
        ),
        headers=_headers(),
        json={
            "actor": _actor(),
            "expected_version": created["version"],
            "credential": "credential-test-value",
        },
    ).json()
    tested = client.post(
        (
            "/v1/control-plane/fmcc/billing/provider-accounts/"
            f"{created['provider_account_id']}/test-connection"
        ),
        headers=_headers(),
        json={
            "actor": _actor(),
            "expected_version": stored["version"],
        },
    ).json()
    assert tested["ok"] is True

    activated = client.post(
        (
            "/v1/control-plane/fmcc/billing/provider-accounts/"
            f"{created['provider_account_id']}/status"
        ),
        headers=_headers(),
        json={
            "actor": _actor(),
            "expected_version": tested["account"]["version"],
            "status": "active",
        },
    )

    assert activated.status_code == 400
    assert (
        activated.json()["error"]
        == "billing_provider_production_legal_entity_required"
    )
