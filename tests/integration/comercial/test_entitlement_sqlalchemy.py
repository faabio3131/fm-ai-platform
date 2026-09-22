from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_catalog import AplicacaoCatalogoComercialV1
from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from core.comercial.catalogo import EntitlementPlano, StatusConfiguracaoCatalogo
from core.comercial.entitlement import (
    EntitlementNegado,
    EstadoComercial,
    ModoAcessoComercial,
)
from core.comercial.modelos import ClasseContaComercial, StatusContaProduto
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.comercial.entitlement_orm import (
    KordenaEntitlementInboxORM,
    KordenaEntitlementProjectionORM,
)
from infra.comercial.modelos_orm import CommercialOutboxORM
from migrations.runner import run_migrations


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return (
        factory,
        AplicacaoCommercialRegistryV1(factory),
        AplicacaoCatalogoComercialV1(factory),
        AplicacaoEntitlementComercialV1(factory, stale_grace_seconds=60),
    )


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="internal-fm",
        unidade_id="internal-fm-hq",
        usuario_id="director-test",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="kca04-correlation",
        solicitado_em=datetime.now(timezone.utc),
        origem="kca04-test",
        unidades_permitidas=frozenset({"internal-fm-hq"}),
        identity_user_id="director-global-test",
        membership_id="director-membership-test",
        product_code="KORDENA",
    )


def _preparar_conta_e_plano(registry, catalog):
    customer = registry.criar_cliente(
        contexto=_contexto(),
        idempotency_key="kca04-customer",
        display_name="Cliente KCA04",
        legal_name=None,
        account_class=ClasseContaComercial.TRIAL,
        primary_contact_email="kca04@example.com",
        primary_contact_phone=None,
    )
    account = registry.criar_conta_produto(
        contexto=_contexto(),
        idempotency_key="kca04-account",
        fm_customer_id=customer.fm_customer_id,
        product_code="KORDENA",
        product_tenant_id="tenant-kca04",
    )
    account = registry.transicionar_conta_produto(
        contexto=_contexto(),
        product_account_id=account.product_account_id,
        expected_version=account.version,
        status=StatusContaProduto.ACTIVE,
        product_tenant_id="tenant-kca04",
    )

    draft = catalog.criar_versao_plano(
        contexto=_contexto(),
        idempotency_key="kca04-plan-a",
        plan_code="KORDENA_PLAN_A",
        display_name="Plano A KCA04",
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
            EntitlementPlano(
                capability_key="core_ai.enabled",
                enabled=False,
                limit_value=None,
                limit_unit=None,
                config={},
            ),
        ),
        change_reason="configuracao kca04",
    )
    validated = catalog.validar_versao_plano(
        contexto=_contexto(),
        plan_version_id=draft.plan_version_id,
        change_reason="validacao kca04",
    )
    assert validated.status == StatusConfiguracaoCatalogo.VALIDATED
    published = catalog.publicar_versao_plano(
        contexto=_contexto(),
        idempotency_key="kca04-plan-publish",
        plan_version_id=draft.plan_version_id,
        expected_plan_version=1,
        effective_from=datetime.now(timezone.utc) - timedelta(seconds=1),
        change_reason="publicacao kca04",
    )
    return account, published


def _event_payload(snapshot):
    from core.comercial.entitlement import serializar_capabilities

    return {
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
    }


def test_snapshot_event_projection_e_gate_capability() -> None:
    factory, registry, catalog, entitlement = _infra()
    account, published = _preparar_conta_e_plano(registry, catalog)

    snapshot = entitlement.recalcular(
        contexto=_contexto(),
        idempotency_key="kca04-entitlement-1",
        product_account_id=account.product_account_id,
        tenant_id="tenant-kca04",
        commercial_state=EstadoComercial.TRIAL_ACTIVE,
        plan_code="KORDENA_PLAN_A",
        valid_until=datetime.now(timezone.utc) + timedelta(minutes=10),
        change_reason="ativacao de teste",
    )
    retry = entitlement.recalcular(
        contexto=_contexto(),
        idempotency_key="kca04-entitlement-1",
        product_account_id=account.product_account_id,
        tenant_id="tenant-kca04",
        commercial_state=EstadoComercial.TRIAL_ACTIVE,
        plan_code="KORDENA_PLAN_A",
        valid_until=snapshot.valid_until,
        change_reason="ativacao de teste",
    )
    assert retry.entitlement_snapshot_id == snapshot.entitlement_snapshot_id
    assert snapshot.plan_version_id == published.plan_version_id
    assert snapshot.access_mode == ModoAcessoComercial.FULL
    assert snapshot.revision == 1

    with factory() as session:
        event = session.scalar(
            select(CommercialOutboxORM).where(
                CommercialOutboxORM.event_type == "entitlement.changed"
            )
        )
    assert event is not None
    assert entitlement.aplicar_evento_local(
        event_id=event.event_id,
        payload=dict(event.payload),
    ) is True

    decision = entitlement.exigir_capacidade(
        tenant_id="tenant-kca04",
        product_account_id=account.product_account_id,
        capability_key="users.max",
    )
    assert decision.allowed is True
    assert decision.revision == 1

    with pytest.raises(EntitlementNegado, match="capability_not_entitled"):
        entitlement.exigir_capacidade(
            tenant_id="tenant-kca04",
            product_account_id=account.product_account_id,
            capability_key="core_ai.enabled",
        )


def test_missing_e_stale_excedido_sao_fail_closed() -> None:
    _, registry, catalog, entitlement = _infra()
    account, _ = _preparar_conta_e_plano(registry, catalog)

    missing = entitlement.avaliar_local(
        tenant_id="tenant-kca04",
        product_account_id=account.product_account_id,
    )
    assert missing.allowed is False
    assert missing.access_mode == ModoAcessoComercial.BLOCKED

    snapshot = entitlement.recalcular(
        contexto=_contexto(),
        idempotency_key="kca04-entitlement-stale",
        product_account_id=account.product_account_id,
        tenant_id="tenant-kca04",
        commercial_state=EstadoComercial.TRIAL_ACTIVE,
        plan_code="KORDENA_PLAN_A",
        valid_until=datetime.now(timezone.utc) + timedelta(seconds=1),
        change_reason="stale test",
    )
    assert entitlement.aplicar_evento_local(
        event_id="evt-stale",
        payload=_event_payload(snapshot),
    )

    inside_grace = entitlement.avaliar_local(
        tenant_id="tenant-kca04",
        product_account_id=account.product_account_id,
        agora=snapshot.valid_until + timedelta(seconds=30),
    )
    assert inside_grace.allowed is True
    assert inside_grace.stale is True

    expired = entitlement.avaliar_local(
        tenant_id="tenant-kca04",
        product_account_id=account.product_account_id,
        agora=snapshot.valid_until + timedelta(seconds=61),
    )
    assert expired.allowed is False
    assert expired.access_mode == ModoAcessoComercial.BLOCKED
    assert expired.reason == "entitlement_stale_limit_exceeded"


def test_duplicate_e_out_of_order_nao_regredem_projection() -> None:
    factory, registry, catalog, entitlement = _infra()
    account, _ = _preparar_conta_e_plano(registry, catalog)
    now = datetime.now(timezone.utc)
    base = {
        "product_account_id": account.product_account_id,
        "tenant_id": "tenant-kca04",
        "commercial_state": "trial_active",
        "plan_code": "KORDENA_PLAN_A",
        "plan_version_id": "pv-test",
        "access_mode": "full",
        "capabilities": {},
        "effective_from": now.isoformat(),
        "valid_until": (now + timedelta(minutes=5)).isoformat(),
    }

    assert entitlement.aplicar_evento_local(
        event_id="evt-r2", payload={**base, "revision": 2}
    ) is True
    assert entitlement.aplicar_evento_local(
        event_id="evt-r1", payload={**base, "revision": 1}
    ) is False
    assert entitlement.aplicar_evento_local(
        event_id="evt-r2", payload={**base, "revision": 2}
    ) is False

    with factory() as session:
        projection = session.get(KordenaEntitlementProjectionORM, "tenant-kca04")
        inbox = session.scalars(select(KordenaEntitlementInboxORM)).all()
    assert projection is not None
    assert projection.revision == 2
    assert len(inbox) == 2


def test_recalculo_rejeita_cross_tenant() -> None:
    _, registry, catalog, entitlement = _infra()
    account, _ = _preparar_conta_e_plano(registry, catalog)

    with pytest.raises(EntitlementNegado, match="tenant_product_account_mismatch"):
        entitlement.recalcular(
            contexto=_contexto(),
            idempotency_key="cross-tenant",
            product_account_id=account.product_account_id,
            tenant_id="tenant-outro",
            commercial_state=EstadoComercial.TRIAL_ACTIVE,
            plan_code="KORDENA_PLAN_A",
            valid_until=datetime.now(timezone.utc) + timedelta(minutes=5),
            change_reason="deve falhar",
        )
