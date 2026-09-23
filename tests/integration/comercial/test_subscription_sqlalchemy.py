from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from application.commercial_subscription import AplicacaoSubscriptionComercialV1
from application.commercial_trial import AplicacaoTrialComercialV1
from core.comercial.entitlement import ModoAcessoComercial
from core.comercial.erros import ConflitoIdempotenciaComercial, DadoComercialInvalido
from core.comercial.modelos import ClasseContaComercial, StatusContaProduto
from core.comercial.subscription import EstadoAssinatura
from core.comercial.trial import EstadoTrial
from core.seguranca.contexto import ContextoExecucao
from infra.comercial.catalogo_orm import (
    FMCommercialPlanORM,
    FMCommercialPlanVersionORM,
    FMCommercialPriceORM,
)
from migrations.runner import run_migrations


PLAN_A_VERSION = "kca08-plan-a-v1"
PLAN_B_VERSION = "kca08-plan-b-v1"
PRICE_A = "kca08-price-a-monthly"
PRICE_B = "kca08-price-b-monthly"


def _context(tenant_id: str) -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="kca08-test",
        motivo="KCA-08 integration",
        tenant_id=tenant_id,
        unidade_id=f"unit-{tenant_id}",
        correlation_id=f"corr-{tenant_id}",
        solicitado_em=datetime.now(timezone.utc),
    )


def _factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory() as session, session.begin():
        for code, version_id, price_id, amount, rank in (
            ("KORDENA_PLAN_A", PLAN_A_VERSION, PRICE_A, Decimal("99.90"), 1),
            ("KORDENA_PLAN_B", PLAN_B_VERSION, PRICE_B, Decimal("149.90"), 2),
        ):
            plan = session.scalar(
                select(FMCommercialPlanORM).where(
                    FMCommercialPlanORM.plan_code == code
                )
            )
            assert plan is not None
            plan.status = "configured"
            plan.version = 2
            plan.updated_at = now
            session.add(
                FMCommercialPlanVersionORM(
                    plan_version_id=version_id,
                    plan_id=plan.plan_id,
                    version_number=1,
                    display_name=f"Plano KCA08 {rank}",
                    description=None,
                    trial_eligible=True,
                    marketing_badge=None,
                    metadata_json={"test_only": True},
                    status="published",
                    valid_from=now - timedelta(days=1),
                    valid_until=None,
                    change_reason="fixture KCA-08",
                    created_by="test",
                    validated_by="test",
                    published_by="test",
                    created_at=now,
                    validated_at=now,
                    published_at=now,
                )
            )
            session.add(
                FMCommercialPriceORM(
                    price_id=price_id,
                    plan_version_id=version_id,
                    revision=1,
                    currency="BRL",
                    billing_period="MONTHLY",
                    amount=amount,
                    change_policy="new_customers_only",
                    status="published",
                    valid_from=now - timedelta(days=1),
                    valid_until=None,
                    change_reason="fixture KCA-08",
                    created_by="test",
                    validated_by="test",
                    published_by="test",
                    created_at=now,
                    validated_at=now,
                    published_at=now,
                )
            )
    return factory


def _account(factory, *, tenant_id: str):
    context = _context(tenant_id)
    registry = AplicacaoCommercialRegistryV1(factory)
    customer = registry.criar_cliente(
        contexto=context,
        idempotency_key=f"customer-{tenant_id}",
        display_name=f"Cliente {tenant_id}",
        legal_name=None,
        account_class=ClasseContaComercial.TRIAL,
        primary_contact_email=f"{tenant_id}@example.invalid",
        primary_contact_phone=None,
    )
    account = registry.criar_conta_produto(
        contexto=context,
        idempotency_key=f"account-{tenant_id}",
        fm_customer_id=customer.fm_customer_id,
        product_code="KORDENA",
    )
    account = registry.transicionar_conta_produto(
        contexto=context,
        product_account_id=account.product_account_id,
        expected_version=account.version,
        status=StatusContaProduto.ACTIVE,
        product_tenant_id=tenant_id,
    )
    return context, customer, account


def _pending(factory, *, tenant_id: str = "tenant-kca08"):
    context, customer, account = _account(factory, tenant_id=tenant_id)
    app = AplicacaoSubscriptionComercialV1(factory)
    subscription = app.criar_pendente(
        contexto=context,
        idempotency_key=f"subscription-{tenant_id}",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id=tenant_id,
        plan_code="KORDENA_PLAN_A",
        plan_version_id=PLAN_A_VERSION,
        price_id=PRICE_A,
    )
    return context, customer, account, app, subscription


def test_trial_conversion_subscription_activation_and_entitlement_are_coordinated() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-convert")
    trial_app = AplicacaoTrialComercialV1(factory)
    trial = trial_app.ativar(
        contexto=context,
        idempotency_key="trial-convert",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-convert",
        email_verified=True,
    ).trial
    assert trial.status == EstadoTrial.ACTIVE

    app = AplicacaoSubscriptionComercialV1(factory)
    pending = app.criar_pendente(
        contexto=context,
        idempotency_key="sub-convert",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-convert",
        plan_code="KORDENA_PLAN_A",
        plan_version_id=PLAN_A_VERSION,
        price_id=PRICE_A,
    )
    now = datetime.now(timezone.utc)
    result = app.ativar(
        contexto=context,
        subscription_id=pending.subscription_id,
        expected_version=pending.version,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    assert result.subscription.status == EstadoAssinatura.ACTIVE
    converted = trial_app.obter_por_product_account(
        product_account_id=account.product_account_id
    )
    assert converted is not None
    assert converted.status == EstadoTrial.CONVERTED

    decision = AplicacaoEntitlementComercialV1(factory).avaliar_local(
        tenant_id="tenant-convert",
        product_account_id=account.product_account_id,
    )
    assert decision.allowed is True
    assert decision.access_mode == ModoAcessoComercial.FULL


def test_subscription_create_is_idempotent_and_conflicting_payload_fails() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-idem")
    app = AplicacaoSubscriptionComercialV1(factory)
    first = app.criar_pendente(
        contexto=context,
        idempotency_key="same-key",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-idem",
        plan_code="KORDENA_PLAN_A",
        plan_version_id=PLAN_A_VERSION,
        price_id=PRICE_A,
    )
    retry = app.criar_pendente(
        contexto=context,
        idempotency_key="same-key",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-idem",
        plan_code="KORDENA_PLAN_A",
        plan_version_id=PLAN_A_VERSION,
        price_id=PRICE_A,
    )
    assert retry.subscription_id == first.subscription_id

    with pytest.raises(
        ConflitoIdempotenciaComercial,
        match="subscription_idempotency_payload_conflict",
    ):
        app.criar_pendente(
            contexto=context,
            idempotency_key="same-key",
            fm_customer_id=customer.fm_customer_id,
            product_account_id=account.product_account_id,
            tenant_id="tenant-idem",
            plan_code="KORDENA_PLAN_B",
            plan_version_id=PLAN_B_VERSION,
            price_id=PRICE_B,
        )


def test_subscription_lifecycle_recovery_cancel_and_renewal() -> None:
    factory = _factory()
    context, _, _, app, pending = _pending(factory, tenant_id="tenant-life")
    now = datetime.now(timezone.utc)
    active = app.ativar(
        contexto=context,
        subscription_id=pending.subscription_id,
        expected_version=pending.version,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    ).subscription
    past_due = app.marcar_past_due(
        contexto=context,
        subscription_id=active.subscription_id,
        expected_version=active.version,
    )
    assert past_due.status == EstadoAssinatura.PAST_DUE

    recovered = app.reativar(
        contexto=context,
        subscription_id=past_due.subscription_id,
        expected_version=past_due.version,
    )
    suspended = app.suspender(
        contexto=context,
        subscription_id=recovered.subscription_id,
        expected_version=recovered.version,
        motivo="teste de suspensão",
    )
    assert suspended.status == EstadoAssinatura.SUSPENDED
    active_again = app.reativar(
        contexto=context,
        subscription_id=suspended.subscription_id,
        expected_version=suspended.version,
    )

    renewed = app.renovar(
        contexto=context,
        subscription_id=active_again.subscription_id,
        expected_version=active_again.version,
        current_period_start=now + timedelta(days=30),
        current_period_end=now + timedelta(days=60),
    )
    assert renewed.current_period_end is not None

    scheduled = app.agendar_cancelamento_fim_periodo(
        contexto=context,
        subscription_id=renewed.subscription_id,
        expected_version=renewed.version,
    )
    assert scheduled.cancel_at_period_end is True

    canceled = app.cancelar(
        contexto=context,
        subscription_id=scheduled.subscription_id,
        expected_version=scheduled.version,
        motivo="cancelamento solicitado",
    )
    assert canceled.status == EstadoAssinatura.CANCELED
    assert canceled.cancel_at_period_end is False


def test_plan_change_preserves_explicit_version_and_price_binding() -> None:
    factory = _factory()
    context, _, _, app, pending = _pending(factory, tenant_id="tenant-plan")
    changed = app.alterar_plano(
        contexto=context,
        subscription_id=pending.subscription_id,
        expected_version=pending.version,
        plan_code="KORDENA_PLAN_B",
        plan_version_id=PLAN_B_VERSION,
        price_id=PRICE_B,
    )
    assert changed.plan_code == "KORDENA_PLAN_B"
    assert changed.plan_version_id == PLAN_B_VERSION
    assert changed.price_id == PRICE_B
    assert changed.contracted_amount == Decimal("149.90")


def test_cross_tenant_and_invalid_price_binding_fail_closed() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-sec")
    app = AplicacaoSubscriptionComercialV1(factory)

    with pytest.raises(
        PermissionError,
        match="tenant_product_account_mismatch",
    ):
        app.criar_pendente(
            contexto=context,
            idempotency_key="cross-tenant",
            fm_customer_id=customer.fm_customer_id,
            product_account_id=account.product_account_id,
            tenant_id="tenant-other",
            plan_code="KORDENA_PLAN_A",
            plan_version_id=PLAN_A_VERSION,
            price_id=PRICE_A,
        )

    with pytest.raises(
        DadoComercialInvalido,
        match="price_plan_version_mismatch",
    ):
        app.criar_pendente(
            contexto=context,
            idempotency_key="bad-price",
            fm_customer_id=customer.fm_customer_id,
            product_account_id=account.product_account_id,
            tenant_id="tenant-sec",
            plan_code="KORDENA_PLAN_A",
            plan_version_id=PLAN_A_VERSION,
            price_id=PRICE_B,
        )

def test_expired_trial_subscription_activation_restores_entitlement_idempotently() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-kca11-recovery")
    trial_app = AplicacaoTrialComercialV1(factory)
    trial = trial_app.ativar(
        contexto=context,
        idempotency_key="kca11-recovery-trial",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-kca11-recovery",
        email_verified=True,
    ).trial
    assert trial.ends_at is not None

    expired = trial_app.expirar(
        contexto=context,
        trial_id=trial.trial_id,
        agora=trial.ends_at,
    )
    assert expired.status == EstadoTrial.EXPIRED

    blocked = AplicacaoEntitlementComercialV1(factory).avaliar_local(
        tenant_id="tenant-kca11-recovery",
        product_account_id=account.product_account_id,
    )
    assert blocked.allowed is False
    assert blocked.access_mode == ModoAcessoComercial.BILLING_ONLY

    app = AplicacaoSubscriptionComercialV1(factory)
    pending = app.criar_pendente(
        contexto=context,
        idempotency_key="kca11-recovery-subscription",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-kca11-recovery",
        plan_code="KORDENA_PLAN_A",
        plan_version_id=PLAN_A_VERSION,
        price_id=PRICE_A,
    )
    now = datetime.now(timezone.utc)
    first = app.ativar(
        contexto=context,
        subscription_id=pending.subscription_id,
        expected_version=pending.version,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    assert first.subscription.status == EstadoAssinatura.ACTIVE

    recovered = AplicacaoEntitlementComercialV1(factory).avaliar_local(
        tenant_id="tenant-kca11-recovery",
        product_account_id=account.product_account_id,
    )
    assert recovered.allowed is True
    assert recovered.access_mode == ModoAcessoComercial.FULL

    repeated = app.ativar(
        contexto=context,
        subscription_id=first.subscription.subscription_id,
        expected_version=first.subscription.version,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    assert repeated.subscription.subscription_id == first.subscription.subscription_id
    assert repeated.entitlement_snapshot_id == first.entitlement_snapshot_id

    still_recovered = AplicacaoEntitlementComercialV1(factory).avaliar_local(
        tenant_id="tenant-kca11-recovery",
        product_account_id=account.product_account_id,
    )
    assert still_recovered.allowed is True
    assert still_recovered.access_mode == ModoAcessoComercial.FULL

