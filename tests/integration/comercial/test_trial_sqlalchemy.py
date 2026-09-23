from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from application.commercial_trial import AplicacaoTrialComercialV1
from core.comercial.entitlement import ModoAcessoComercial
from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
)
from core.comercial.modelos import ClasseContaComercial, StatusContaProduto
from core.comercial.trial import EstadoTrial
from core.seguranca.contexto import ContextoExecucao
from infra.comercial.catalogo_orm import FMCommercialPlanORM, FMCommercialPlanVersionORM
from infra.comercial.modelos_orm import CommercialOutboxORM
from migrations.runner import run_migrations


def _context(tenant_id: str) -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="kca07-test",
        motivo="KCA-07 integration",
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
        plan = session.scalar(
            select(FMCommercialPlanORM).where(
                FMCommercialPlanORM.plan_code == "KORDENA_PLAN_A"
            )
        )
        assert plan is not None
        plan.status = "configured"
        plan.version = 2
        plan.updated_at = now
        session.add(
            FMCommercialPlanVersionORM(
                plan_version_id="kca07-test-plan-version-a",
                plan_id=plan.plan_id,
                version_number=1,
                display_name="Plano de teste KCA-07",
                description=None,
                trial_eligible=True,
                marketing_badge=None,
                metadata_json={},
                status="published",
                valid_from=now - timedelta(days=1),
                valid_until=None,
                change_reason="fixture KCA-07",
                created_by="test",
                validated_by="test",
                published_by="test",
                created_at=now,
                validated_at=now,
                published_at=now,
            )
        )
    return factory


def _account(factory, *, tenant_id: str, account_class=ClasseContaComercial.TRIAL):
    context = _context(tenant_id)
    registry = AplicacaoCommercialRegistryV1(factory)
    customer = registry.criar_cliente(
        contexto=context,
        idempotency_key=f"customer-{tenant_id}",
        display_name=f"Cliente {tenant_id}",
        legal_name=None,
        account_class=account_class,
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


def test_trial_activates_for_exactly_30_days_and_projects_full_entitlement() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-trial-a")
    app = AplicacaoTrialComercialV1(factory)

    first = app.ativar(
        contexto=context,
        idempotency_key="trial-a",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-trial-a",
        email_verified=True,
    )
    repeated = app.ativar(
        contexto=context,
        idempotency_key="trial-a",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-trial-a",
        email_verified=True,
    )

    assert repeated.trial.trial_id == first.trial.trial_id
    assert first.trial.status == EstadoTrial.ACTIVE
    assert first.trial.started_at is not None
    assert first.trial.ends_at == first.trial.started_at + timedelta(days=30)
    assert first.trial.policy_version == "KORDENA_TRIAL_30D_V1"

    decision = AplicacaoEntitlementComercialV1(factory).avaliar_local(
        tenant_id="tenant-trial-a",
        product_account_id=account.product_account_id,
    )
    assert decision.allowed is True
    assert decision.access_mode == ModoAcessoComercial.FULL

    with factory() as session:
        events = set(session.scalars(select(CommercialOutboxORM.event_type)))
    assert {"trial.created", "trial.activated", "entitlement.changed"} <= events


def test_trial_rejects_unverified_email_and_cross_tenant_binding() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-trial-b")
    app = AplicacaoTrialComercialV1(factory)

    with pytest.raises(DadoComercialInvalido, match="trial_email_not_verified"):
        app.ativar(
            contexto=context,
            idempotency_key="unverified",
            fm_customer_id=customer.fm_customer_id,
            product_account_id=account.product_account_id,
            tenant_id="tenant-trial-b",
            email_verified=False,
        )

    with pytest.raises(
        DadoComercialInvalido,
        match="trial_tenant_product_account_mismatch",
    ):
        app.ativar(
            contexto=ContextoExecucao.sistema(
                identidade="kca07-test",
                motivo="cross tenant denial",
                tenant_id="tenant-other",
                unidade_id="unit-other",
                correlation_id="corr-other",
                solicitado_em=datetime.now(timezone.utc),
            ),
            idempotency_key="cross-tenant",
            fm_customer_id=customer.fm_customer_id,
            product_account_id=account.product_account_id,
            tenant_id="tenant-other",
            email_verified=True,
        )


def test_trial_idempotency_conflict_is_explicit() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-trial-c")
    app = AplicacaoTrialComercialV1(factory)
    app.ativar(
        contexto=context,
        idempotency_key="same-key",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-trial-c",
        email_verified=True,
    )
    with pytest.raises(
        ConflitoIdempotenciaComercial,
        match="trial_idempotency_payload_conflict",
    ):
        app.ativar(
            contexto=context,
            idempotency_key="same-key",
            fm_customer_id=customer.fm_customer_id,
            product_account_id=account.product_account_id,
            tenant_id="tenant-trial-c",
            email_verified=True,
            override_antiabuse=True,
            override_reason="different request",
        )


def test_trial_expiration_boundary_is_exact_and_retry_safe() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-trial-d")
    app = AplicacaoTrialComercialV1(factory)
    active = app.ativar(
        contexto=context,
        idempotency_key="expire",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-trial-d",
        email_verified=True,
    ).trial
    assert active.ends_at is not None

    with pytest.raises(DadoComercialInvalido, match="trial_not_expired_yet"):
        app.expirar(
            contexto=context,
            trial_id=active.trial_id,
            agora=active.ends_at - timedelta(microseconds=1),
        )

    expired = app.expirar(
        contexto=context,
        trial_id=active.trial_id,
        agora=active.ends_at,
    )
    again = app.expirar(
        contexto=context,
        trial_id=active.trial_id,
        agora=active.ends_at + timedelta(seconds=1),
    )
    assert expired.status == EstadoTrial.EXPIRED
    assert again.trial_id == expired.trial_id

    decision = AplicacaoEntitlementComercialV1(factory).avaliar_local(
        tenant_id="tenant-trial-d",
        product_account_id=account.product_account_id,
    )
    assert decision.allowed is False
    assert decision.access_mode == ModoAcessoComercial.BILLING_ONLY


def test_customer_trial_history_requires_audited_override() -> None:
    factory = _factory()
    context_a, customer, account_a = _account(factory, tenant_id="tenant-trial-e")
    app = AplicacaoTrialComercialV1(factory)
    app.ativar(
        contexto=context_a,
        idempotency_key="history-a",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account_a.product_account_id,
        tenant_id="tenant-trial-e",
        email_verified=True,
    )

    registry = AplicacaoCommercialRegistryV1(factory)
    context_b = _context("tenant-trial-e2")
    account_b = registry.criar_conta_produto(
        contexto=context_b,
        idempotency_key="history-account-b",
        fm_customer_id=customer.fm_customer_id,
        product_code="KORDENA",
    )
    account_b = registry.transicionar_conta_produto(
        contexto=context_b,
        product_account_id=account_b.product_account_id,
        expected_version=account_b.version,
        status=StatusContaProduto.ACTIVE,
        product_tenant_id="tenant-trial-e2",
    )

    with pytest.raises(
        RegistroComercialDuplicado,
        match="trial_customer_history_not_eligible",
    ):
        app.ativar(
            contexto=context_b,
            idempotency_key="history-b",
            fm_customer_id=customer.fm_customer_id,
            product_account_id=account_b.product_account_id,
            tenant_id="tenant-trial-e2",
            email_verified=True,
        )

    overridden = app.ativar(
        contexto=context_b,
        idempotency_key="history-b-override",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account_b.product_account_id,
        tenant_id="tenant-trial-e2",
        email_verified=True,
        override_antiabuse=True,
        override_reason="approved test override",
    )
    assert overridden.trial.override_reason == "approved test override"


def test_internal_test_trial_marks_commercial_event_as_kpi_excluded() -> None:
    factory = _factory()
    context, customer, account = _account(
        factory,
        tenant_id="tenant-trial-internal",
        account_class=ClasseContaComercial.INTERNAL_TEST,
    )
    trial = AplicacaoTrialComercialV1(factory).ativar(
        contexto=context,
        idempotency_key="internal",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-trial-internal",
        email_verified=True,
    ).trial

    with factory() as session:
        event = session.scalar(
            select(CommercialOutboxORM).where(
                CommercialOutboxORM.event_type == "trial.activated",
                CommercialOutboxORM.aggregate_id == trial.trial_id,
            )
        )
    assert event is not None
    assert event.payload["kpi_excluded"] is True

def test_late_expiration_batch_is_reprocessable_and_does_not_extend_trial() -> None:
    factory = _factory()
    context, customer, account = _account(factory, tenant_id="tenant-kca11-late")
    app = AplicacaoTrialComercialV1(factory)
    active = app.ativar(
        contexto=context,
        idempotency_key="kca11-late-trial",
        fm_customer_id=customer.fm_customer_id,
        product_account_id=account.product_account_id,
        tenant_id="tenant-kca11-late",
        email_verified=True,
    ).trial
    assert active.ends_at is not None

    late_clock = active.ends_at + timedelta(hours=2)
    expired = app.expirar_vencidos(
        contexto_factory=lambda _: context,
        agora=late_clock,
        limite=10,
    )
    assert len(expired) == 1
    assert expired[0].trial_id == active.trial_id
    assert expired[0].status == EstadoTrial.EXPIRED

    repeated = app.expirar_vencidos(
        contexto_factory=lambda _: context,
        agora=late_clock + timedelta(minutes=1),
        limite=10,
    )
    assert repeated == ()

    decision = AplicacaoEntitlementComercialV1(factory).avaliar_local(
        tenant_id="tenant-kca11-late",
        product_account_id=account.product_account_id,
        agora=late_clock,
    )
    assert decision.allowed is False
    assert decision.access_mode == ModoAcessoComercial.BILLING_ONLY
