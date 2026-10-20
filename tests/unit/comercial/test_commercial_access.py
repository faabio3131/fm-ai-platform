from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_access import AplicacaoAcessoComercialV1
from application.commercial_catalog import AplicacaoCatalogoComercialV1
from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from core.comercial.catalogo import EntitlementPlano
from core.comercial.entitlement import EstadoComercial, ModoAcessoComercial
from core.comercial.modelos import ClasseContaComercial, StatusContaProduto
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from migrations.runner import run_migrations


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="fm-internal",
        unidade_id="hq",
        usuario_id="director",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="kca11-access",
        solicitado_em=datetime.now(timezone.utc),
        origem="kca11-test",
        unidades_permitidas=frozenset({"hq"}),
        identity_user_id="director-global",
        membership_id="director-membership",
        product_code="KORDENA",
    )


def _managed_trial(factory, *, valid_until: datetime):
    registry = AplicacaoCommercialRegistryV1(factory)
    catalog = AplicacaoCatalogoComercialV1(factory)
    customer = registry.criar_cliente(
        contexto=_contexto(),
        idempotency_key="kca11-customer",
        display_name="KCA11 Customer",
        legal_name=None,
        account_class=ClasseContaComercial.TRIAL,
        primary_contact_email="kca11@example.com",
        primary_contact_phone=None,
    )
    account = registry.criar_conta_produto(
        contexto=_contexto(),
        idempotency_key="kca11-account",
        fm_customer_id=customer.fm_customer_id,
        product_code="KORDENA",
        product_tenant_id="tenant-kca11",
    )
    account = registry.transicionar_conta_produto(
        contexto=_contexto(),
        product_account_id=account.product_account_id,
        expected_version=account.version,
        status=StatusContaProduto.ACTIVE,
        product_tenant_id="tenant-kca11",
    )
    draft = catalog.criar_versao_plano(
        contexto=_contexto(),
        idempotency_key="kca11-plan",
        plan_code="KORDENA_PLAN_A",
        display_name="Plano A KCA11",
        description=None,
        trial_eligible=True,
        marketing_badge=None,
        metadata={"test_only": True},
        entitlements=(
            EntitlementPlano(
                capability_key="users.max",
                enabled=True,
                limit_value=Decimal("5"),
                limit_unit="users",
                config={},
            ),
        ),
        change_reason="kca11",
    )
    catalog.validar_versao_plano(
        contexto=_contexto(),
        plan_version_id=draft.plan_version_id,
        change_reason="kca11",
    )
    catalog.publicar_versao_plano(
        contexto=_contexto(),
        idempotency_key="kca11-plan-publish",
        plan_version_id=draft.plan_version_id,
        expected_plan_version=1,
        effective_from=datetime.now(timezone.utc) - timedelta(seconds=1),
        change_reason="kca11",
    )
    entitlement = AplicacaoEntitlementComercialV1(factory)
    snapshot = entitlement.recalcular(
        contexto=_contexto(),
        idempotency_key="kca11-entitlement",
        product_account_id=account.product_account_id,
        tenant_id="tenant-kca11",
        commercial_state=EstadoComercial.TRIAL_ACTIVE,
        plan_code="KORDENA_PLAN_A",
        valid_until=valid_until,
        change_reason="kca11 trial",
    )
    entitlement.aplicar_evento_local(
        event_id="kca11-entitlement-event",
        payload={
            "product_account_id": snapshot.product_account_id,
            "tenant_id": snapshot.tenant_id,
            "revision": snapshot.revision,
            "commercial_state": snapshot.commercial_state.value,
            "plan_code": snapshot.plan_code,
            "plan_version_id": snapshot.plan_version_id,
            "access_mode": snapshot.access_mode.value,
            "capabilities": {
                item.capability_key: {
                    "enabled": item.enabled,
                    "limit_value": (
                        str(item.limit_value)
                        if item.limit_value is not None
                        else None
                    ),
                    "limit_unit": item.limit_unit,
                    "config": dict(item.config),
                }
                for item in snapshot.capabilities
            },
            "effective_from": snapshot.effective_from.isoformat(),
            "valid_until": snapshot.valid_until.isoformat(),
        },
    )
    return account, snapshot


def test_gate_disabled_preserva_tenant_v1_sem_product_account() -> None:
    factory = _infra()
    result = AplicacaoAcessoComercialV1(
        factory,
        enforcement_enabled=False,
    ).avaliar(tenant_id="tenant-legado")

    assert result.managed is False
    assert result.operational_allowed is True
    assert result.reason == "commercial_gate_disabled_legacy_unmanaged"


def test_gate_enabled_falha_fechado_sem_product_account() -> None:
    factory = _infra()
    result = AplicacaoAcessoComercialV1(
        factory,
        enforcement_enabled=True,
    ).avaliar(tenant_id="tenant-sem-binding")

    assert result.managed is False
    assert result.operational_allowed is False
    assert result.access_mode == ModoAcessoComercial.BLOCKED
    assert result.reason == "product_account_missing"


def test_trial_expirado_bloqueia_no_boundary_mesmo_com_stale_grace() -> None:
    factory = _infra()
    now = datetime.now(timezone.utc)
    _, snapshot = _managed_trial(
        factory,
        valid_until=now + timedelta(seconds=5),
    )

    result = AplicacaoAcessoComercialV1(
        factory,
        enforcement_enabled=True,
        stale_grace_seconds=300,
    ).avaliar(
        tenant_id="tenant-kca11",
        agora=snapshot.valid_until,
    )

    assert result.managed is True
    assert result.operational_allowed is False
    assert result.entitled is False
    assert result.access_mode == ModoAcessoComercial.BILLING_ONLY
    assert result.reason == "trial_expired_temporally"


def test_trial_valido_permanece_operacional_antes_do_boundary() -> None:
    factory = _infra()
    now = datetime.now(timezone.utc)
    _, snapshot = _managed_trial(
        factory,
        valid_until=now + timedelta(minutes=5),
    )

    result = AplicacaoAcessoComercialV1(
        factory,
        enforcement_enabled=True,
        stale_grace_seconds=300,
    ).avaliar(
        tenant_id="tenant-kca11",
        agora=snapshot.valid_until - timedelta(microseconds=1),
    )

    assert result.managed is True
    assert result.operational_allowed is True
    assert result.entitled is True
    assert result.access_mode == ModoAcessoComercial.FULL
    assert result.reason == "entitlement_active"
