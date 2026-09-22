from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SENHA = "Senha-KCA01-Admin-123"
TENANT = "internal-fm"
UNIDADE = "internal-fm-hq"


def _infra(monkeypatch, *, papel: Papel = Papel.ADMINISTRADOR):
    monkeypatch.setenv("FM_AI_SESSION_SECRET", "kca01-session-secret-012345678901234")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="kca01-admin",
            email="director@example.com",
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(papel,),
            unidades_permitidas=(UNIDADE,),
        )
        session.commit()

    client = TestClient(
        build_frontend_http_app(
            settings=RuntimeSettings(
                environment=RuntimeEnvironment.TEST,
                database_url="sqlite://",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
            ),
            engine=engine,
            session_factory=factory,
        )
    )
    return client


def _login(client: TestClient, *, step_up: bool = True) -> None:
    assert client.post(
        "/v1/auth/login",
        json={"email": "director@example.com", "senha": SENHA},
    ).status_code == 200
    if step_up:
        assert client.post(
            "/v1/auth/admin-step-up",
            json={"senha": SENHA},
        ).status_code == 200


def test_commercial_registry_exige_sessao_e_stepup(monkeypatch) -> None:
    client = _infra(monkeypatch)
    payload = {
        "display_name": "Cliente",
        "legal_name": None,
        "account_class": "internal_test",
        "primary_contact_email": "owner@example.com",
        "primary_contact_phone": None,
    }

    assert client.post(
        "/v1/admin/commercial/customers",
        headers={"Idempotency-Key": "api-customer"},
        json=payload,
    ).status_code == 401

    _login(client, step_up=False)
    assert client.post(
        "/v1/admin/commercial/customers",
        headers={"Idempotency-Key": "api-customer"},
        json=payload,
    ).status_code == 403


def test_admin_cria_customer_e_product_account_sem_confiar_headers_de_tenant(
    monkeypatch,
) -> None:
    client = _infra(monkeypatch)
    _login(client)

    response = client.post(
        "/v1/admin/commercial/customers",
        headers={
            "Idempotency-Key": "api-customer",
            "X-Tenant-ID": "tenant-forjado",
            "X-Unit-ID": "unit-forjada",
            "X-Correlation-ID": "kca01-api",
        },
        json={
            "display_name": "Cliente Interno",
            "legal_name": None,
            "account_class": "internal_test",
            "primary_contact_email": "owner@example.com",
            "primary_contact_phone": None,
        },
    )
    assert response.status_code == 201
    customer = response.json()
    assert customer["account_class"] == "internal_test"

    retry = client.post(
        "/v1/admin/commercial/customers",
        headers={"Idempotency-Key": "api-customer"},
        json={
            "display_name": "Cliente Interno",
            "legal_name": None,
            "account_class": "internal_test",
            "primary_contact_email": "owner@example.com",
            "primary_contact_phone": None,
        },
    )
    assert retry.status_code == 201
    assert retry.json()["fm_customer_id"] == customer["fm_customer_id"]

    account_response = client.post(
        (
            f"/v1/admin/commercial/customers/{customer['fm_customer_id']}"
            "/product-accounts"
        ),
        headers={"Idempotency-Key": "api-pa"},
        json={"product_code": "KORDENA", "product_tenant_id": None},
    )
    assert account_response.status_code == 201
    account = account_response.json()
    assert account["status"] == "requested"

    activation = client.post(
        (
            "/v1/admin/commercial/product-accounts/"
            f"{account['product_account_id']}/transition"
        ),
        json={
            "expected_version": 1,
            "status": "active",
            "product_tenant_id": "tenant-kordena-homolog",
        },
    )
    assert activation.status_code == 200
    assert activation.json()["product_tenant_id"] == "tenant-kordena-homolog"


def test_gerente_nao_recebe_administracao_comercial(monkeypatch) -> None:
    client = _infra(monkeypatch, papel=Papel.GERENTE)
    _login(client, step_up=False)
    response = client.get("/v1/admin/commercial/customers/qualquer")
    assert response.status_code == 403


def test_nao_existe_signup_publico_no_kca01(monkeypatch) -> None:
    client = _infra(monkeypatch)
    assert client.post("/v1/public/signup", json={}).status_code == 404



def test_billing_configuration_requires_stepup_and_hides_secret_reference(
    monkeypatch,
) -> None:
    client = _infra(monkeypatch)
    payload = {
        "provider_code": "PROVIDER_CONFIGURAVEL",
        "display_name": "Conta principal FM",
        "legal_entity_ref": None,
        "environment": "sandbox",
        "credential_secret_reference": "env:FM_BILLING_PROVIDER_TEST",
        "supported_payment_methods": ["pix", "card"],
        "supports_recurring": True,
        "supports_webhooks": True,
        "priority": 10,
    }

    assert client.post(
        "/v1/admin/commercial/billing/provider-accounts",
        headers={"Idempotency-Key": "billing-provider-api"},
        json=payload,
    ).status_code == 401

    _login(client, step_up=False)
    assert client.post(
        "/v1/admin/commercial/billing/provider-accounts",
        headers={"Idempotency-Key": "billing-provider-api"},
        json=payload,
    ).status_code == 403

    assert client.post(
        "/v1/auth/admin-step-up",
        json={"senha": SENHA},
    ).status_code == 200

    response = client.post(
        "/v1/admin/commercial/billing/provider-accounts",
        headers={"Idempotency-Key": "billing-provider-api"},
        json=payload,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["provider_code"] == "PROVIDER_CONFIGURAVEL"
    assert body["credential_configured"] is True
    assert "credential_secret_reference" not in body

    listing = client.get("/v1/admin/commercial/billing/provider-accounts")
    assert listing.status_code == 200
    assert len(listing.json()) == 1
    assert "credential_secret_reference" not in listing.json()[0]


def test_gerente_nao_configura_contas_de_recebimento(monkeypatch) -> None:
    client = _infra(monkeypatch, papel=Papel.GERENTE)
    _login(client, step_up=False)
    response = client.get("/v1/admin/commercial/billing/provider-accounts")
    assert response.status_code == 403
