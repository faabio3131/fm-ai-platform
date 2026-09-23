from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.comercial_registry import AplicacaoCommercialRegistryV1
from core.comercial.modelos import ClasseContaComercial, StatusContaProduto
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from http_api.fmcc_commercial_control import build_fmcc_commercial_control_router
from migrations.runner import run_migrations

TOKEN = "kca12-fmcc-control-plane-token-0123456789abcdef"


def _admin_context() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="fm-internal",
        unidade_id="hq",
        usuario_id="director",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="kca12-fixture",
        solicitado_em=datetime.now(timezone.utc),
        origem="kca12-test",
        unidades_permitidas=frozenset({"hq"}),
        identity_user_id="director-global",
        membership_id="director-membership",
        product_code="KORDENA",
    )


def _client(*, token: str | None = TOKEN) -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    registry = AplicacaoCommercialRegistryV1(factory)
    customer = registry.criar_cliente(
        contexto=_admin_context(),
        idempotency_key="kca12-customer-a",
        display_name="KCA12 Customer A",
        legal_name=None,
        account_class=ClasseContaComercial.TRIAL,
        primary_contact_email="secret-contact@example.test",
        primary_contact_phone="+5511999999999",
    )
    account = registry.criar_conta_produto(
        contexto=_admin_context(),
        idempotency_key="kca12-account-a",
        fm_customer_id=customer.fm_customer_id,
        product_code="KORDENA",
        product_tenant_id="tenant-kca12-a",
    )
    registry.transicionar_conta_produto(
        contexto=_admin_context(),
        product_account_id=account.product_account_id,
        expected_version=account.version,
        status=StatusContaProduto.ACTIVE,
        product_tenant_id="tenant-kca12-a",
    )

    app = FastAPI()
    app.state.kca12_session_factory = factory
    app.include_router(
        build_fmcc_commercial_control_router(
            session_factory=factory,
            control_plane_token=token,
        )
    )
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Idempotency-Key": "kca12-command-001",
        "X-Correlation-ID": "kca12-corr-001",
    }


def _actor(*, age: timedelta = timedelta()) -> dict[str, str]:
    return {
        "user_id": "fmcc-owner-1",
        "role": "owner",
        "step_up_at": (
            datetime.now(timezone.utc) - age
        ).isoformat(),
    }


def test_snapshot_is_authenticated_and_does_not_expose_contact_pii() -> None:
    client = _client()

    denied = client.get("/v1/control-plane/fmcc/snapshot")
    assert denied.status_code == 401

    response = client.get(
        "/v1/control-plane/fmcc/snapshot",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "kordena.fmcc.commercial.v1"
    assert payload["product_code"] == "KORDENA"
    assert payload["summary"]["customers"] == 1
    assert (
        payload["product_accounts"][0]["product_tenant_id"]
        == "tenant-kca12-a"
    )
    assert payload["coverage"]["mrr"] == "pending_governed_semantics"
    assert payload["coverage"]["organization_users_units"] == "safe_counts_only"
    assert "secret-contact@example.test" not in response.text
    assert "+5511999999999" not in response.text


def test_boundary_fails_closed_without_configured_service_secret() -> None:
    client = _client(token=None)
    response = client.get(
        "/v1/control-plane/fmcc/health",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "fmcc_control_plane_not_configured"


def test_catalog_command_requires_fresh_step_up() -> None:
    client = _client()

    stale = client.post(
        "/v1/control-plane/fmcc/catalog/commands",
        headers=_headers(),
        json={
            "actor": _actor(age=timedelta(minutes=16)),
            "action": "plan_version.create",
            "resource_id": "KORDENA_PLAN_A",
            "payload": {
                "display_name": "Plano A KCA12",
                "description": "Configurado pelo FMCC",
                "trial_eligible": True,
                "marketing_badge": None,
                "metadata": {},
                "entitlements": [],
                "change_reason": "KCA-12 integration test",
            },
        },
    )
    assert stale.status_code == 403
    assert stale.json()["error"] == "fmcc_control_plane.step_up_required"

    accepted = client.post(
        "/v1/control-plane/fmcc/catalog/commands",
        headers=_headers(),
        json={
            "actor": _actor(),
            "action": "plan_version.create",
            "resource_id": "KORDENA_PLAN_A",
            "payload": {
                "display_name": "Plano A KCA12",
                "description": "Configurado pelo FMCC",
                "trial_eligible": True,
                "marketing_badge": None,
                "metadata": {},
                "entitlements": [],
                "change_reason": "KCA-12 integration test",
            },
        },
    )
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["status"] == "accepted"
    assert body["action"] == "plan_version.create"
    assert body["result"]["display_name"] == "Plano A KCA12"
    assert body["result"]["status"] == "draft"

    preview = client.post(
        "/v1/control-plane/fmcc/catalog/commands",
        headers={
            **_headers(),
            "Idempotency-Key": "kca12-command-preview",
        },
        json={
            "actor": _actor(),
            "action": "plan_version.preview",
            "resource_id": body["result"]["plan_version_id"],
            "payload": {},
        },
    )
    assert preview.status_code == 200
    assert preview.json()["action"] == "plan_version.preview"
    assert "result" in preview.json()

    repeated = client.post(
        "/v1/control-plane/fmcc/catalog/commands",
        headers=_headers(),
        json={
            "actor": _actor(),
            "action": "plan_version.create",
            "resource_id": "KORDENA_PLAN_A",
            "payload": {
                "display_name": "Plano A KCA12",
                "description": "Configurado pelo FMCC",
                "trial_eligible": True,
                "marketing_badge": None,
                "metadata": {},
                "entitlements": [],
                "change_reason": "KCA-12 integration test",
            },
        },
    )
    assert repeated.status_code == 200
    assert (
        repeated.json()["result"]["plan_version_id"]
        == body["result"]["plan_version_id"]
    )

    factory = client.app.state.kca12_session_factory
    with factory() as session:
        version_count = session.scalar(
            select(func.count(FMCommercialPlanVersionORM.plan_version_id)).where(
                FMCommercialPlanVersionORM.plan_version_id
                == body["result"]["plan_version_id"]
            )
        )
        audits = session.scalars(
            select(CommercialAuditORM).where(
                CommercialAuditORM.action == "commercial.plan_version.create",
                CommercialAuditORM.aggregate_id
                == body["result"]["plan_version_id"],
            )
        ).all()

    assert version_count == 1
    assert body["result"]["version_number"] == 1
    assert len(audits) == 1
    assert audits[0].actor_user_id == "fmcc-owner-1"
    assert audits[0].metadata_safe["version_number"] == 1


def test_wrong_service_token_is_rejected_before_command_execution() -> None:
    client = _client()
    response = client.post(
        "/v1/control-plane/fmcc/catalog/commands",
        headers={
            "Authorization": "Bearer wrong-wrong-wrong-wrong-wrong-wrong-wrong",
            "Idempotency-Key": "kca12-command-denied",
        },
        json={
            "actor": _actor(),
            "action": "plan_version.create",
            "resource_id": "KORDENA_PLAN_A",
            "payload": {},
        },
    )
    assert response.status_code == 401
