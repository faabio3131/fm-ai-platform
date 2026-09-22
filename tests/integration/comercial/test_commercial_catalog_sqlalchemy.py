from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.commercial_catalog import AplicacaoCatalogoComercialV1
from core.comercial.catalogo import (
    EntitlementPlano,
    PoliticaMudancaPreco,
    StatusConfiguracaoCatalogo,
    StatusRegistroCatalogo,
    TipoDescontoPromocao,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.comercial.catalogo_orm import (
    FMCommercialPlanORM,
    FMCommercialPlanVersionORM,
    FMCommercialPriceORM,
)
from infra.comercial.modelos_orm import CommercialAuditORM, CommercialOutboxORM
from migrations.runner import run_migrations


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return factory, AplicacaoCatalogoComercialV1(factory)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="internal-fm",
        unidade_id="internal-fm-hq",
        usuario_id="director-test",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="kca03-correlation",
        solicitado_em=datetime.now(timezone.utc),
        origem="kca03-test",
        unidades_permitidas=frozenset({"internal-fm-hq"}),
        identity_user_id="director-global-test",
        membership_id="director-membership-test",
        product_code="KORDENA",
    )


def _entitlements() -> tuple[EntitlementPlano, ...]:
    return (
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
    )


def _criar_publicar_plano(app: AplicacaoCatalogoComercialV1):
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    draft = app.criar_versao_plano(
        contexto=_contexto(),
        idempotency_key="plan-a-v1",
        plan_code="KORDENA_PLAN_A",
        display_name="Plano A Teste",
        description="Nome temporário de teste",
        trial_eligible=True,
        marketing_badge=None,
        metadata={"test_only": True},
        entitlements=_entitlements(),
        change_reason="configuracao de teste KCA-03",
    )
    validated = app.validar_versao_plano(
        contexto=_contexto(),
        plan_version_id=draft.plan_version_id,
        change_reason="revisao de teste",
    )
    assert validated.status == StatusConfiguracaoCatalogo.VALIDATED
    published = app.publicar_versao_plano(
        contexto=_contexto(),
        idempotency_key="plan-a-v1-publish",
        plan_version_id=draft.plan_version_id,
        expected_plan_version=1,
        effective_from=now,
        change_reason="publicacao de teste",
    )
    return published


def test_migration_semeia_exatamente_quatro_planos_sem_nome_ou_preco_hardcoded() -> None:
    factory, app = _infra()

    catalog = app.listar_catalogo_kordena(contexto=_contexto())
    assert [item["plan"].plan_code for item in catalog] == [
        "KORDENA_PLAN_A",
        "KORDENA_PLAN_B",
        "KORDENA_PLAN_C",
        "KORDENA_PLAN_D",
    ]
    assert [item["plan"].rank for item in catalog] == [1, 2, 3, 4]
    assert all(item["effective_version"] is None for item in catalog)
    assert all(item["effective_prices"] == () for item in catalog)

    with factory() as session:
        plans = session.scalars(
            select(FMCommercialPlanORM).order_by(FMCommercialPlanORM.rank)
        ).all()
        versions = session.scalars(select(FMCommercialPlanVersionORM)).all()
        prices = session.scalars(select(FMCommercialPriceORM)).all()

    assert len(plans) == 4
    assert all(plan.status == "configuration_pending" for plan in plans)
    assert versions == []
    assert prices == []


def test_plan_version_idempotente_valida_publica_e_emite_outbox() -> None:
    factory, app = _infra()
    first = app.criar_versao_plano(
        contexto=_contexto(),
        idempotency_key="same-plan-draft",
        plan_code="KORDENA_PLAN_A",
        display_name="Plano A Teste",
        description=None,
        trial_eligible=True,
        marketing_badge="teste",
        metadata={},
        entitlements=_entitlements(),
        change_reason="rascunho",
    )
    retry = app.criar_versao_plano(
        contexto=_contexto(),
        idempotency_key="same-plan-draft",
        plan_code="KORDENA_PLAN_A",
        display_name="Plano A Teste",
        description=None,
        trial_eligible=True,
        marketing_badge="teste",
        metadata={},
        entitlements=_entitlements(),
        change_reason="rascunho",
    )
    assert first == retry
    assert first.status == StatusConfiguracaoCatalogo.DRAFT

    preview = app.preview_versao_plano(
        contexto=_contexto(),
        plan_version_id=first.plan_version_id,
    )
    assert preview["changes"] == {"initial_configuration": True}

    app.validar_versao_plano(
        contexto=_contexto(),
        plan_version_id=first.plan_version_id,
        change_reason="validado",
    )
    published = app.publicar_versao_plano(
        contexto=_contexto(),
        idempotency_key="publish-plan-a",
        plan_version_id=first.plan_version_id,
        expected_plan_version=1,
        effective_from=datetime.now(timezone.utc) - timedelta(seconds=1),
        change_reason="publicado",
    )
    assert published.status == StatusConfiguracaoCatalogo.PUBLISHED

    catalog = app.listar_catalogo_kordena(contexto=_contexto())
    plan_a = catalog[0]
    assert plan_a["plan"].status == StatusRegistroCatalogo.CONFIGURED
    assert plan_a["effective_version"].plan_version_id == published.plan_version_id

    with factory() as session:
        events = session.scalars(select(CommercialOutboxORM)).all()
        audit = session.scalars(select(CommercialAuditORM)).all()
    assert any(event.event_type == "plan.version.published" for event in events)
    assert any(row.action == "commercial.plan_version.publish" for row in audit)


def test_price_e_versionado_agendavel_e_nao_reescreve_historico() -> None:
    factory, app = _infra()
    plan_version = _criar_publicar_plano(app)

    first = app.criar_preco(
        contexto=_contexto(),
        idempotency_key="price-r1",
        plan_version_id=plan_version.plan_version_id,
        currency="BRL",
        billing_period="MONTHLY",
        amount=Decimal("99.90"),
        change_policy=PoliticaMudancaPreco.NEW_CUSTOMERS_ONLY,
        change_reason="preco de teste inicial",
    )
    app.validar_preco(
        contexto=_contexto(),
        price_id=first.price_id,
        change_reason="validacao preco inicial",
    )
    first = app.publicar_preco(
        contexto=_contexto(),
        idempotency_key="price-r1-publish",
        price_id=first.price_id,
        expected_plan_version=2,
        effective_from=datetime.now(timezone.utc) - timedelta(seconds=1),
        change_reason="publicar preco inicial",
    )
    assert first.revision == 1
    assert first.amount == Decimal("99.90")

    second = app.criar_preco(
        contexto=_contexto(),
        idempotency_key="price-r2",
        plan_version_id=plan_version.plan_version_id,
        currency="brl",
        billing_period="monthly",
        amount=Decimal("119.90"),
        change_policy=PoliticaMudancaPreco.NEW_CUSTOMERS_ONLY,
        change_reason="reajuste futuro de teste",
    )
    preview = app.preview_preco(contexto=_contexto(), price_id=second.price_id)
    assert preview["amount_change"] == {
        "before": Decimal("99.90"),
        "after": Decimal("119.90"),
    }

    app.validar_preco(
        contexto=_contexto(),
        price_id=second.price_id,
        change_reason="validar reajuste",
    )
    future = datetime.now(timezone.utc) + timedelta(days=30)
    second = app.publicar_preco(
        contexto=_contexto(),
        idempotency_key="price-r2-publish",
        price_id=second.price_id,
        expected_plan_version=3,
        effective_from=future,
        change_reason="agendar reajuste",
    )
    assert second.revision == 2
    assert second.valid_from == future

    with factory() as session:
        rows = session.scalars(
            select(FMCommercialPriceORM)
            .where(
                FMCommercialPriceORM.plan_version_id
                == plan_version.plan_version_id
            )
            .order_by(FMCommercialPriceORM.revision)
        ).all()
    assert Decimal(rows[0].amount) == Decimal("99.90")
    assert rows[0].valid_until is not None
    assert Decimal(rows[1].amount) == Decimal("119.90")


def test_nova_versao_de_plano_futura_preserva_versao_atual_ate_a_data() -> None:
    _, app = _infra()
    first = _criar_publicar_plano(app)

    second = app.criar_versao_plano(
        contexto=_contexto(),
        idempotency_key="plan-a-v2",
        plan_code="KORDENA_PLAN_A",
        display_name="Novo Nome Futuro",
        description="Mudanca agendada",
        trial_eligible=True,
        marketing_badge=None,
        metadata={},
        entitlements=_entitlements(),
        change_reason="versao futura",
    )
    app.validar_versao_plano(
        contexto=_contexto(),
        plan_version_id=second.plan_version_id,
        change_reason="validar versao futura",
    )
    future = datetime.now(timezone.utc) + timedelta(days=10)
    second = app.publicar_versao_plano(
        contexto=_contexto(),
        idempotency_key="plan-a-v2-publish",
        plan_version_id=second.plan_version_id,
        expected_plan_version=2,
        effective_from=future,
        change_reason="agendar versao futura",
    )

    now_catalog = app.listar_catalogo_kordena(
        contexto=_contexto(),
        instante=datetime.now(timezone.utc),
    )
    future_catalog = app.listar_catalogo_kordena(
        contexto=_contexto(),
        instante=future + timedelta(seconds=1),
    )
    assert now_catalog[0]["effective_version"].plan_version_id == first.plan_version_id
    assert future_catalog[0]["effective_version"].plan_version_id == second.plan_version_id


def test_promocao_versionada_preserva_planos_e_publica_evento() -> None:
    factory, app = _infra()
    promotion, draft = app.criar_promocao(
        contexto=_contexto(),
        idempotency_key="promo-1",
        name="Campanha de Teste",
        discount_type=TipoDescontoPromocao.PERCENTAGE,
        discount_value=Decimal("20"),
        currency=None,
        starts_at=datetime.now(timezone.utc) + timedelta(days=1),
        ends_at=datetime.now(timezone.utc) + timedelta(days=10),
        eligible_plan_codes=("KORDENA_PLAN_A", "KORDENA_PLAN_B"),
        max_redemptions=100,
        per_customer_limit=1,
        rules={"test_only": True},
        change_reason="campanha de homologacao",
    )
    assert promotion.status == StatusRegistroCatalogo.CONFIGURATION_PENDING
    assert draft.eligible_plan_codes == ("KORDENA_PLAN_A", "KORDENA_PLAN_B")

    app.validar_versao_promocao(
        contexto=_contexto(),
        promotion_version_id=draft.promotion_version_id,
        change_reason="validar campanha",
    )
    published = app.publicar_versao_promocao(
        contexto=_contexto(),
        idempotency_key="promo-1-publish",
        promotion_version_id=draft.promotion_version_id,
        expected_promotion_version=1,
        change_reason="publicar campanha",
    )
    assert published.status == StatusConfiguracaoCatalogo.PUBLISHED

    rows = app.listar_promocoes(contexto=_contexto())
    assert rows[0]["promotion"].status == StatusRegistroCatalogo.CONFIGURED
    assert (
        rows[0]["latest_published_version"].promotion_version_id
        == published.promotion_version_id
    )

    with factory() as session:
        events = session.scalars(select(CommercialOutboxORM)).all()
    assert any(
        event.event_type == "promotion.version.published"
        for event in events
    )
