from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from core.comercial.entitlement import EstadoComercial, serializar_capabilities
from core.comercial.modelos import ClasseContaComercial, StatusContaProduto
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "kca11-http-session-secret-0123456789-abcdef"
PASSWORD = "Senha-Segura-KCA11-123"
EMAIL = "kca11-operador@example.com"
USER_ID = "usuario-kca11-http"
TENANT = "tenant-kca11-http"
UNIT = "unit-kca11-http"


def _admin_context() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="fm-internal",
        unidade_id="hq",
        usuario_id="director",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="kca11-http-fixture",
        solicitado_em=datetime.now(timezone.utc),
        origem="kca11-http-test",
        unidades_permitidas=frozenset({"hq"}),
        identity_user_id="director-global",
        membership_id="director-membership",
        product_code="KORDENA",
    )


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id=USER_ID,
            email=EMAIL,
            password=PASSWORD,
            tenant_id=TENANT,
            unidade_padrao_id=UNIT,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIT,),
        )
        session.commit()

    registry = AplicacaoCommercialRegistryV1(factory)
    customer = registry.criar_cliente(
        contexto=_admin_context(),
        idempotency_key="kca11-http-customer",
        display_name="KCA11 HTTP Customer",
        legal_name=None,
        account_class=ClasseContaComercial.TRIAL,
        primary_contact_email="customer-kca11-http@example.com",
        primary_contact_phone=None,
    )
    account = registry.criar_conta_produto(
        contexto=_admin_context(),
        idempotency_key="kca11-http-account",
        fm_customer_id=customer.fm_customer_id,
        product_code="KORDENA",
        product_tenant_id=TENANT,
    )
    account = registry.transicionar_conta_produto(
        contexto=_admin_context(),
        product_account_id=account.product_account_id,
        expected_version=account.version,
        status=StatusContaProduto.ACTIVE,
        product_tenant_id=TENANT,
    )

    entitlement = AplicacaoEntitlementComercialV1(factory)
    snapshot = entitlement.recalcular(
        contexto=_admin_context(),
        idempotency_key="kca11-http-expired-entitlement",
        product_account_id=account.product_account_id,
        tenant_id=TENANT,
        commercial_state=EstadoComercial.TRIAL_EXPIRED,
        plan_code=None,
        valid_until=datetime.now(timezone.utc) + timedelta(hours=1),
        change_reason="fixture paywall KCA-11",
    )
    assert entitlement.aplicar_evento_local(
        event_id="kca11-http-expired-event",
        payload={
            "product_account_id": snapshot.product_account_id,
            "tenant_id": snapshot.tenant_id,
            "revision": snapshot.revision,
            "commercial_state": snapshot.commercial_state.value,
            "plan_code": snapshot.plan_code,
            "plan_version_id": snapshot.plan_version_id,
            "access_mode": snapshot.access_mode.value,
            "capabilities": serializar_capabilities(snapshot.capabilities),
            "effective_from": snapshot.effective_from.isoformat(),
            "valid_until": snapshot.valid_until.isoformat(),
        },
    )

    app = build_frontend_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT,
            unidade_id=UNIT,
            commercial_access_gate_enabled=True,
        ),
        engine=engine,
        session_factory=factory,
        commercial_access_gate_enabled=True,
    )
    return TestClient(app)


def _login(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": PASSWORD},
    )
    assert response.status_code == 200


def test_paywall_bloqueia_api_operacional_mas_preserva_auth_e_comercial(
    monkeypatch,
) -> None:
    client = _client(monkeypatch)
    _login(client)

    auth = client.get("/v1/auth/me")
    assert auth.status_code == 200

    commercial = client.get("/v1/commercial/access")
    assert commercial.status_code == 200
    assert commercial.json()["operational_allowed"] is False
    assert commercial.json()["access_mode"] == "billing_only"

    plans = client.get("/v1/commercial/plans")
    assert plans.status_code == 200

    operational = client.get("/v1/pdv/produtos")
    assert operational.status_code == 402
    assert operational.json()["erro"] == "commercial_access_restricted"
    assert operational.json()["access_mode"] == "billing_only"
