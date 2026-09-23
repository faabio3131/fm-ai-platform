"""KCA-15 internal homologation on a real ephemeral PostgreSQL staging runtime.

This runner intentionally does not use FM_AI_TEST_MODE, production credentials,
real billing, or external customer data. It creates a persisted INTERNAL_TEST
identity and exercises the canonical application/HTTP boundaries end to end.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, create_engine, insert, select
from sqlalchemy.orm import sessionmaker

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from core.comercial.entitlement import EstadoComercial, serializar_capabilities
from core.comercial.modelos import ClasseContaComercial, StatusContaProduto
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from http_api.frontend_app import build_frontend_http_app
from infra.administracao.repositorio_sqlalchemy import (\n    RepositorioAdministracaoSQLAlchemy,\n)
from infra.legacy_product_scope import inserir_produto_legado
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

TENANT = "kca15-internal-tenant"
UNIT = "kca15-internal-unit"
EMAIL = "fabio-kca15-internal@example.test"
DISPLAY_NAME = "Fabio — Homologacao Nova FM"
LOJA_ID = 15015


def _context() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="fm-internal",
        unidade_id="fm-hq",
        usuario_id="kca15-homologation-director",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="kca15-internal-homologation",
        solicitado_em=datetime.now(timezone.utc),
        origem="kca15_internal_homologation",
        unidades_permitidas=frozenset({"fm-hq"}),
        identity_user_id="kca15-director-global",
        membership_id="kca15-director-membership",
        product_code="KORDENA",
    )


def _ensure_legacy_scope_and_identity(factory, password: str) -> str:
    with factory() as session, session.begin():
        admin = RepositorioAdministracaoSQLAlchemy(session)
        admin.garantir_escopo(
            tenant_id=TENANT,
            unidade_id=UNIT,
            nome_empresa=DISPLAY_NAME,
            nome_unidade="Unidade Homologacao KCA-15",
        )

        metadata = MetaData()
        lojas = Table("lojas", metadata, autoload_with=session.connection())
        mapping = Table(
            "fm_unidade_loja_legacy_v1",
            metadata,
            autoload_with=session.connection(),
        )
        if session.execute(
            select(lojas.c.id).where(lojas.c.id == LOJA_ID)
        ).scalar_one_or_none() is None:
            session.execute(
                insert(lojas).values(
                    id=LOJA_ID,
                    nome_fantasia="KCA-15 Homologacao Interna",
                )
            )
        if session.execute(
            select(mapping.c.tenant_id)
            .where(mapping.c.tenant_id == TENANT)
            .where(mapping.c.unidade_id == UNIT)
        ).scalar_one_or_none() is None:
            session.execute(
                insert(mapping).values(
                    tenant_id=TENANT,
                    unidade_id=UNIT,
                    loja_id=LOJA_ID,
                    ativo=True,
                )
            )

        identities = RepositorioIdentidadesSQLAlchemy(session)
        identity = identities.obter_por_email(EMAIL)
        if identity is None:
            identity = identities.criar_usuario(
                usuario_id="kca15-internal-director",
                email=EMAIL,
                password=password,
                tenant_id=TENANT,
                unidade_padrao_id=UNIT,
                papeis=(Papel.ADMINISTRADOR,),
                unidades_permitidas=(UNIT,),
                acesso_admin_sensivel=True,
            )

        produtos = Table("produtos", MetaData(), autoload_with=session.connection())
        existing_product = session.execute(
            select(produtos.c.id)
            .where(produtos.c.nome == "Produto KCA-15")
            .where(produtos.c.loja_id == str(LOJA_ID))
        ).scalar_one_or_none()
        if existing_product is None:
            inserir_produto_legado(
                session,
                tenant_id=TENANT,
                unidade_id=UNIT,
                valores={
                    "nome": "Produto KCA-15",
                    "categoria": "Homologacao",
                    "descricao_bruta": "Homologacao interna KCA-15",
                    "descricao_ai": "Homologacao interna KCA-15",
                    "preco_venda": 10.0,
                    "custo_total_cmv": 2.5,
                    "margem_exibicao": "75.0%",
                },
            )
        return str(identity.membership_subject_id)


def _create_internal_commercial_state(factory):
    registry = AplicacaoCommercialRegistryV1(factory)
    context = _context()
    customer = registry.criar_cliente(
        contexto=context,
        idempotency_key="kca15-internal-customer",
        display_name=DISPLAY_NAME,
        legal_name=None,
        account_class=ClasseContaComercial.INTERNAL_TEST,
        primary_contact_email=EMAIL,
        primary_contact_phone=None,
    )
    account = registry.criar_conta_produto(
        contexto=context,
        idempotency_key="kca15-internal-product-account",
        fm_customer_id=customer.fm_customer_id,
        product_code="KORDENA",
        product_tenant_id=TENANT,
    )
    if account.status != StatusContaProduto.ACTIVE:
        account = registry.transicionar_conta_produto(
            contexto=context,
            product_account_id=account.product_account_id,
            expected_version=account.version,
            status=StatusContaProduto.ACTIVE,
            product_tenant_id=TENANT,
        )

    entitlement = AplicacaoEntitlementComercialV1(factory)
    snapshot = entitlement.recalcular(
        contexto=context,
        idempotency_key="kca15-internal-entitlement",
        product_account_id=account.product_account_id,
        tenant_id=TENANT,
        commercial_state=EstadoComercial.INTERNAL_TEST,
        plan_code=None,
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        change_reason="KCA-15 internal homologation",
    )
    applied = entitlement.aplicar_evento_local(
        event_id="kca15-internal-entitlement-event",
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
    assert applied is True
    return customer, account, snapshot


def _fmcc_headers(token: str, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": key,
        "X-Correlation-ID": "kca15-fmcc-homologation",
    }


def _actor() -> dict[str, str]:
    return {
        "user_id": "kca15-internal-director",
        "role": "owner",
        "step_up_at": datetime.now(timezone.utc).isoformat(),
    }


def run(output: Path) -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("KCA-15 homologation must not run with FM_AI_TEST_MODE=1")

    database_url = os.environ["DATABASE_URL"].strip()
    password = os.environ["KCA15_INTERNAL_PASSWORD"]
    session_secret = os.environ["FM_AI_SESSION_SECRET"]
    fmcc_token = os.environ["FM_AI_FMCC_CONTROL_PLANE_TOKEN"]
    if not database_url.startswith("postgresql"):
        raise RuntimeError("KCA-15 requires ephemeral PostgreSQL")
    if len(password) < 16 or len(session_secret) < 32 or len(fmcc_token) < 32:
        raise RuntimeError("KCA-15 generated credentials do not meet minimum length")

    engine = create_engine(database_url, future=True)
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    customer, account, snapshot = _create_internal_commercial_state(factory)
    membership_id = _ensure_legacy_scope_and_identity(factory, password)

    settings = RuntimeSettings(
        environment=RuntimeEnvironment.STAGING,
        database_url=database_url,
        tenant_id="kca15-bootstrap",
        unidade_id="kca15-bootstrap",
        commercial_access_gate_enabled=True,
        fmcc_control_plane_token=fmcc_token,
    ).validate()
    app = build_frontend_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
        commercial_access_gate_enabled=True,
    )
    client = TestClient(app, base_url="https://kca15.local")

    login = client.post("/v1/auth/login", json={"email": EMAIL, "senha": password})
    assert login.status_code == 200, login.text
    me = client.get("/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["tenant_id"] == TENANT
    assert me.json()["unidade_ativa_id"] == UNIT

    units = client.get("/v1/auth/unidades")
    assert units.status_code == 200
    assert {item["id"] for item in units.json()} == {UNIT}

    access = client.get("/v1/commercial/access")
    assert access.status_code == 200, access.text
    assert access.json()["operational_allowed"] is True
    assert access.json()["commercial_state"] == "internal_test"
    assert access.json()["access_mode"] == "full"

    pdv = client.get("/v1/pdv/produtos")
    assert pdv.status_code == 200, pdv.text
    assert any(item["nome"] == "Produto KCA-15" for item in pdv.json()["produtos"])
    salao = client.get("/v1/salao/mapa")
    assert salao.status_code == 200, salao.text
    kds = client.get("/v1/kds/setores")
    assert kds.status_code == 200, kds.text

    pre_step_up = client.post("/v1/admin/acesso")
    assert pre_step_up.status_code == 403
    step_up = client.post("/v1/auth/admin-step-up", json={"senha": password})
    assert step_up.status_code == 200, step_up.text
    admin_access = client.post("/v1/admin/acesso")
    assert admin_access.status_code == 200, admin_access.text

    users = client.get("/v1/admin/usuarios")
    assert users.status_code == 200, users.text
    assert any(row["email"] == EMAIL for row in users.json())

    gerente = client.post(
        "/v1/gerente-ia/tools",
        json={"tool": "consultar_atrasos", "argumentos": {}},
    )
    assert gerente.status_code == 200, gerente.text

    snapshot_response = client.get(
        "/v1/control-plane/fmcc/snapshot",
        headers={"Authorization": f"Bearer {fmcc_token}"},
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    fmcc = snapshot_response.json()
    assert fmcc["summary"]["internal_test_customers"] == 1
    assert fmcc["observability"]["internal_test_excluded"] is True
    assert fmcc["observability"]["metrics"]["trial_started"]["value"] == 0
    assert fmcc["observability"]["metrics"]["subscription_active"]["value"] == 0
    assert fmcc["observability"]["metrics"]["mrr"]["value"]["by_currency"] == []

    plan_create = client.post(
        "/v1/control-plane/fmcc/catalog/commands",
        headers=_fmcc_headers(fmcc_token, "kca15-plan-create"),
        json={
            "actor": _actor(),
            "action": "plan_version.create",
            "resource_id": "KORDENA_PLAN_A",
            "payload": {
                "display_name": "Plano A Homologacao KCA-15",
                "description": "Versao interna de homologacao",
                "trial_eligible": True,
                "marketing_badge": None,
                "metadata": {"internal_test": True},
                "entitlements": [],
                "change_reason": "KCA-15 internal homologation",
            },
        },
    )
    assert plan_create.status_code == 200, plan_create.text
    plan_version = plan_create.json()["result"]
    plan_validate = client.post(
        "/v1/control-plane/fmcc/catalog/commands",
        headers=_fmcc_headers(fmcc_token, "kca15-plan-validate"),
        json={
            "actor": _actor(),
            "action": "plan_version.validate",
            "resource_id": plan_version["plan_version_id"],
            "payload": {"change_reason": "KCA-15 validate plan"},
        },
    )
    assert plan_validate.status_code == 200, plan_validate.text

    promotion_create = client.post(
        "/v1/control-plane/fmcc/catalog/commands",
        headers=_fmcc_headers(fmcc_token, "kca15-promo-create"),
        json={
            "actor": _actor(),
            "action": "promotion.create",
            "payload": {
                "name": "Promocao Homologacao KCA-15",
                "discount_type": "percentage",
                "discount_value": "10",
                "currency": None,
                "starts_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "ends_at": (datetime.now(timezone.utc) + timedelta(days=8)).isoformat(),
                "eligible_plan_codes": ["KORDENA_PLAN_A"],
                "max_redemptions": 10,
                "per_customer_limit": 1,
                "rules": {"internal_test": True},
                "change_reason": "KCA-15 internal homologation",
            },
        },
    )
    assert promotion_create.status_code == 200, promotion_create.text

    logout = client.post("/v1/auth/logout")
    assert logout.status_code == 200, logout.text
    assert client.get("/v1/auth/me").status_code == 401

    evidence = {
        "gate": "KCA-G15",
        "environment": "ephemeral_postgresql_staging",
        "fm_ai_test_mode": False,
        "customer": {
            "fm_customer_id": customer.fm_customer_id,
            "account_class": customer.account_class.value,
        },
        "product_account": {
            "product_account_id": account.product_account_id,
            "tenant_id": account.product_tenant_id,
            "status": account.status.value,
        },
        "identity": {
            "membership_id": membership_id,
            "role": "administrador",
            "tenant_id": TENANT,
            "unit_id": UNIT,
        },
        "entitlement": {
            "snapshot_id": snapshot.entitlement_snapshot_id,
            "commercial_state": snapshot.commercial_state.value,
            "access_mode": snapshot.access_mode.value,
        },
        "checks": {
            "login": "pass",
            "logout": "pass",
            "tenant_unit": "pass",
            "admin_step_up": "pass",
            "pdv": "pass",
            "salao": "pass",
            "kds": "pass",
            "gerente_ia": "pass",
            "fmcc_snapshot": "pass",
            "plan_administration": "pass",
            "promotion_creation": "pass",
            "internal_test_kpi_exclusion": "pass",
        },
        "billing_real_used": False,
        "real_customer_used": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/kca15-internal-homologation.json")
    args = parser.parse_args()
    run(Path(args.output))


if __name__ == "__main__":
    main()
