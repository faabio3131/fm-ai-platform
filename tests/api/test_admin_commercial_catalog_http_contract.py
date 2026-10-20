from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SENHA = "Senha-KCA03-Admin-123"
TENANT = "internal-fm"
UNIDADE = "internal-fm-hq"


def _infra(monkeypatch):
    monkeypatch.setenv("FM_AI_SESSION_SECRET", "kca03-session-secret-012345678901234")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="kca03-director",
            email="director-kca03@example.com",
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.ADMINISTRADOR,),
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
        json={"email": "director-kca03@example.com", "senha": SENHA},
    ).status_code == 200
    if step_up:
        assert client.post(
            "/v1/auth/admin-step-up",
            json={"senha": SENHA},
        ).status_code == 200


def test_catalogo_exige_step_up_e_expoe_quatro_planos_sem_valores(monkeypatch) -> None:
    client = _infra(monkeypatch)

    assert client.get("/v1/admin/commercial/catalog/kordena").status_code == 401
    _login(client, step_up=False)
    assert client.get("/v1/admin/commercial/catalog/kordena").status_code == 403
    assert client.post(
        "/v1/auth/admin-step-up",
        json={"senha": SENHA},
    ).status_code == 200

    response = client.get("/v1/admin/commercial/catalog/kordena")
    assert response.status_code == 200
    body = response.json()
    assert [item["plan"]["plan_code"] for item in body] == [
        "KORDENA_PLAN_A",
        "KORDENA_PLAN_B",
        "KORDENA_PLAN_C",
        "KORDENA_PLAN_D",
    ]
    assert all(item["effective_version"] is None for item in body)
    assert all(item["effective_prices"] == [] for item in body)


def test_admin_configura_plano_publica_preco_e_cria_promocao_sem_deploy(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    create_version = client.post(
        "/v1/admin/commercial/plans/KORDENA_PLAN_A/versions",
        headers={"Idempotency-Key": "api-plan-v1"},
        json={
            "display_name": "Nome Temporario Teste",
            "description": "Configuracao de homologacao",
            "trial_eligible": True,
            "marketing_badge": None,
            "metadata": {"test_only": True},
            "entitlements": [
                {
                    "capability_key": "users.max",
                    "enabled": True,
                    "limit_value": 5,
                    "limit_unit": "users",
                    "config": {},
                }
            ],
            "change_reason": "configuracao KCA03",
        },
    )
    assert create_version.status_code == 201
    plan_version = create_version.json()
    assert plan_version["status"] == "draft"

    preview = client.get(
        f"/v1/admin/commercial/plan-versions/{plan_version['plan_version_id']}/preview"
    )
    assert preview.status_code == 200
    assert preview.json()["changes"]["initial_configuration"] is True

    assert client.post(
        f"/v1/admin/commercial/plan-versions/{plan_version['plan_version_id']}/validate",
        json={"change_reason": "validar plano"},
    ).status_code == 200

    published = client.post(
        f"/v1/admin/commercial/plan-versions/{plan_version['plan_version_id']}/publish",
        headers={"Idempotency-Key": "api-plan-publish"},
        json={
            "expected_plan_version": 1,
            "effective_from": (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat(),
            "change_reason": "publicar plano",
        },
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    price = client.post(
        f"/v1/admin/commercial/plan-versions/{plan_version['plan_version_id']}/prices",
        headers={"Idempotency-Key": "api-price"},
        json={
            "currency": "BRL",
            "billing_period": "MONTHLY",
            "amount": "99.90",
            "change_policy": "new_customers_only",
            "change_reason": "preco apenas de teste",
        },
    )
    assert price.status_code == 201
    price_id = price.json()["price_id"]

    assert client.post(
        f"/v1/admin/commercial/prices/{price_id}/validate",
        json={"change_reason": "validar preco"},
    ).status_code == 200

    price_publish = client.post(
        f"/v1/admin/commercial/prices/{price_id}/publish",
        headers={"Idempotency-Key": "api-price-publish"},
        json={
            "expected_plan_version": 2,
            "effective_from": (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat(),
            "change_reason": "publicar preco",
        },
    )
    assert price_publish.status_code == 200
    assert price_publish.json()["amount"] == "99.90"

    promotion = client.post(
        "/v1/admin/commercial/promotions",
        headers={"Idempotency-Key": "api-promo"},
        json={
            "name": "Promocao de Teste",
            "discount_type": "percentage",
            "discount_value": "20",
            "currency": None,
            "starts_at": (
                datetime.now(timezone.utc) + timedelta(days=1)
            ).isoformat(),
            "ends_at": (
                datetime.now(timezone.utc) + timedelta(days=5)
            ).isoformat(),
            "eligible_plan_codes": ["KORDENA_PLAN_A"],
            "max_redemptions": 50,
            "per_customer_limit": 1,
            "rules": {"test_only": True},
            "change_reason": "promocao de homologacao",
        },
    )
    assert promotion.status_code == 201
    assert promotion.json()["version"]["status"] == "draft"


def test_plan_e_rejeitado_para_codigo_fora_dos_quatro_canonicos(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    response = client.post(
        "/v1/admin/commercial/plans/KORDENA_PLAN_E/versions",
        headers={"Idempotency-Key": "invalid-plan"},
        json={
            "display_name": "Invalido",
            "description": None,
            "trial_eligible": True,
            "marketing_badge": None,
            "metadata": {},
            "entitlements": [],
            "change_reason": "teste invalido",
        },
    )
    assert response.status_code == 400
    assert response.json()["erro"] == "plan_code_nao_canonico"
