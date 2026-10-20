"""Provisionamento automático ao ativar/renovar assinatura, sem IA real."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from application.ai_budget_provision import provisionar_franquias_assinatura
from infra.ai_budget_sqlalchemy import (
    AIBudgetBase, FranquiaAIBudgetORM, LedgerFranquiasIASQLAlchemy,
)
from infra.comercial.entitlement_orm import (
    EntitlementBase, KordenaEntitlementProjectionORM,
)
from infra.comercial.subscription_orm import (
    SubscriptionBase, FMCommercialSubscriptionORM,
)
from infra.seguranca.modelos_orm import (
    GlobalIdentityBase, IdentityUserORM, IdentityMembershipORM,
    IdentityMembershipUnitORM,
)

NOW = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)


def _setup(tmp_path, *, authorize: bool = True, membership: bool = True):
    engine = create_engine(f"sqlite:///{tmp_path / 'provision.db'}")
    for metadata in (
        GlobalIdentityBase.metadata, SubscriptionBase.metadata,
        EntitlementBase.metadata, AIBudgetBase.metadata,
    ):
        metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    capabilities = ({
        "ai.budget.tool_planning": {
            "enabled": True, "limit_value": "1.00", "limit_unit": "USD",
            "config": {"scope": "unit", "maximo_por_tentativa": "0.05"},
        }
    } if authorize else {})
    with factory.begin() as session:
        session.add(FMCommercialSubscriptionORM(
            subscription_id="subscription-a", fm_customer_id="customer-a",
            product_account_id="account-a", tenant_id="tenant-a",
            plan_code="KORDENA_PLAN_A", plan_version_id="plan-version-a",
            price_id="price-a", currency="BRL", billing_period="monthly",
            contracted_amount=Decimal("0"), status="active",
            current_period_start=NOW - timedelta(days=1),
            current_period_end=NOW + timedelta(days=30),
            cancel_at_period_end=False, version=1,
            correlation_id="test-budgets",
        ))
        session.add(KordenaEntitlementProjectionORM(
            tenant_id="tenant-a", product_account_id="account-a",
            revision=3, commercial_state="subscription_active",
            plan_code="KORDENA_PLAN_A", plan_version_id="plan-version-a",
            access_mode="full", capabilities_json=capabilities,
            effective_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=30), last_synced_at=NOW,
        ))
        if membership:
            session.add(IdentityUserORM(
                identity_user_id="user-a", email="user-a@example.invalid",
                senha_hash="fixture", ativo=True,
            ))
            session.add(IdentityMembershipORM(
                membership_id="membership-a", identity_user_id="user-a",
                product_code="KORDENA", tenant_id="tenant-a",
                unidade_padrao_id="unit-a", ativo=True,
                acesso_admin_sensivel=True,
            ))
            session.add_all([
                IdentityMembershipUnitORM(
                    membership_id="membership-a", unidade_id="unit-a"
                ),
                IdentityMembershipUnitORM(
                    membership_id="membership-a", unidade_id="unit-b"
                ),
            ])
    return factory


def _run(factory):
    return provisionar_franquias_assinatura(
        factory,
        tenant_id="tenant-a",
        product_account_id="account-a",
        subscription_id="subscription-a",
    )


def test_franchise_provision_por_unidade_e_idempotente(tmp_path):
    factory = _setup(tmp_path)
    assert _run(factory) == 2
    assert _run(factory) == 2
    with factory() as session:
        budgets = session.scalars(select(FranquiaAIBudgetORM)).all()
        assert {row.unidade_id for row in budgets} == {"unit-a", "unit-b"}
        assert len(budgets) == 2
        assert {row.limite for row in budgets} == {Decimal("1")}
        assert all(row.revisao_politica == 3 for row in budgets)
        assert all(row.consumido == 0 and row.reservado == 0 for row in budgets)


def test_sem_entitlement_autorizado_nao_cria_orcamento(tmp_path):
    factory = _setup(tmp_path, authorize=False)
    assert _run(factory) == 0
    with factory() as session:
        assert session.scalars(select(FranquiaAIBudgetORM)).all() == []


def test_sem_unidades_autorizadas_nao_inventa_unidade(tmp_path):
    factory = _setup(tmp_path, membership=False)
    assert _run(factory) == 0


def test_nao_provisiona_para_outro_cliente_ou_produto(tmp_path):
    factory = _setup(tmp_path)
    assert provisionar_franquias_assinatura(
        factory, tenant_id="tenant-b", product_account_id="account-a",
        subscription_id="subscription-a",
    ) == 0
    assert provisionar_franquias_assinatura(
        factory, tenant_id="tenant-a", product_account_id="account-b",
        subscription_id="subscription-a",
    ) == 0
