from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.commercial_billing import BillingProviderAdapterRegistryV1
from application.commercial_billing_config import AplicacaoBillingConfigurationV1
from core.comercial.billing import BillingConnectionTestResult
from core.comercial.billing_config import (
    BillingConnectionTestStatus,
    BillingEnvironment,
    BillingPaymentMethod,
    BillingProviderAccountStatus,
)
from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    TransicaoComercialInvalida,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import ReferenceSecretStore, SecretValue
from infra.comercial.billing_config_orm import FMBillingProviderAccountORM
from migrations.runner import run_migrations


class FakeConfigProvider:
    def __init__(self, provider_code: str, *, ok: bool = True) -> None:
        self.provider_code = provider_code
        self.ok = ok
        self.seen_credentials: list[str] = []

    def test_connection(
        self,
        *,
        context,
        credential: SecretValue,
    ) -> BillingConnectionTestResult:
        assert context.idempotency_key
        assert context.correlation_id
        self.seen_credentials.append(credential.reveal())
        return BillingConnectionTestResult(
            ok=self.ok,
            provider_code=self.provider_code,
            detail_code="connection_ok" if self.ok else "connection_failed",
        )


def _context() -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="kca09b-test",
        motivo="KCA-09B integration",
        tenant_id="internal-fm",
        unidade_id="internal-fm-hq",
        correlation_id="corr-kca09b",
        solicitado_em=datetime.now(timezone.utc),
    )


def _infra(*providers: FakeConfigProvider):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = BillingProviderAdapterRegistryV1(tuple(providers))
    store = ReferenceSecretStore(
        mapping={
            "alpha": "definitely-fake-secret-alpha",
            "beta": "definitely-fake-secret-beta",
            "fail": "definitely-fake-secret-fail",
        }
    )
    app = AplicacaoBillingConfigurationV1(
        factory,
        adapter_registry=registry,
        secret_store=store,
    )
    return engine, factory, app


def _create_account(
    app: AplicacaoBillingConfigurationV1,
    *,
    key: str,
    provider_code: str,
    secret_ref: str,
    environment: BillingEnvironment = BillingEnvironment.PRODUCTION,
    methods: tuple[BillingPaymentMethod, ...] = (
        BillingPaymentMethod.PIX,
        BillingPaymentMethod.CARD,
    ),
):
    return app.criar_provider_account(
        contexto=_context(),
        idempotency_key=key,
        provider_code=provider_code,
        display_name=f"Conta {provider_code}",
        legal_entity_ref=None,
        environment=environment,
        credential_secret_reference=secret_ref,
        supported_payment_methods=methods,
        supports_recurring=True,
        supports_webhooks=True,
        priority=10,
    )


def _test_and_activate(
    app: AplicacaoBillingConfigurationV1,
    account,
):
    tested = app.testar_conexao(
        contexto=_context(),
        provider_account_id=account.provider_account_id,
        expected_version=account.version,
    )
    assert tested.ok is True
    assert tested.account.last_test_status == BillingConnectionTestStatus.PASS
    return app.transicionar_provider_account(
        contexto=_context(),
        provider_account_id=account.provider_account_id,
        expected_version=tested.account.version,
        status=BillingProviderAccountStatus.ACTIVE,
    )


def test_multiple_accounts_route_primary_and_governed_fallback() -> None:
    alpha = FakeConfigProvider("PROVIDER_ALPHA")
    beta = FakeConfigProvider("PROVIDER_BETA")
    _, _, app = _infra(alpha, beta)

    account_a = _test_and_activate(
        app,
        _create_account(
            app,
            key="account-alpha",
            provider_code="PROVIDER_ALPHA",
            secret_ref="mapping:alpha",
        ),
    )
    account_b = _test_and_activate(
        app,
        _create_account(
            app,
            key="account-beta",
            provider_code="PROVIDER_BETA",
            secret_ref="mapping:beta",
        ),
    )

    policy = app.criar_routing_policy(
        contexto=_context(),
        idempotency_key="route-kordena-pix",
        product_code="KORDENA",
        payment_method=BillingPaymentMethod.PIX,
        environment=BillingEnvironment.PRODUCTION,
        primary_provider_account_id=account_a.provider_account_id,
        fallback_provider_account_ids=(account_b.provider_account_id,),
    )
    assert policy.primary_provider_account_id == account_a.provider_account_id

    route = app.resolver_rota(
        product_code="KORDENA",
        payment_method=BillingPaymentMethod.PIX,
        environment=BillingEnvironment.PRODUCTION,
    )
    assert [item.provider_account_id for item in route.accounts] == [
        account_a.provider_account_id,
        account_b.provider_account_id,
    ]

    suspended = app.transicionar_provider_account(
        contexto=_context(),
        provider_account_id=account_a.provider_account_id,
        expected_version=account_a.version,
        status=BillingProviderAccountStatus.SUSPENDED,
    )
    assert suspended.status == BillingProviderAccountStatus.SUSPENDED

    fallback_route = app.resolver_rota(
        product_code="KORDENA",
        payment_method=BillingPaymentMethod.PIX,
        environment=BillingEnvironment.PRODUCTION,
    )
    assert [item.provider_account_id for item in fallback_route.accounts] == [
        account_b.provider_account_id
    ]


def test_activation_requires_connection_pass_and_route_fails_closed() -> None:
    failing = FakeConfigProvider("PROVIDER_FAIL", ok=False)
    _, _, app = _infra(failing)
    account = _create_account(
        app,
        key="account-fail",
        provider_code="PROVIDER_FAIL",
        secret_ref="mapping:fail",
    )
    tested = app.testar_conexao(
        contexto=_context(),
        provider_account_id=account.provider_account_id,
        expected_version=account.version,
    )
    assert tested.ok is False
    assert tested.account.status == BillingProviderAccountStatus.VALIDATING
    assert tested.account.last_test_status == BillingConnectionTestStatus.FAIL

    with pytest.raises(
        TransicaoComercialInvalida,
        match="activation_requires_connection_test",
    ):
        app.transicionar_provider_account(
            contexto=_context(),
            provider_account_id=account.provider_account_id,
            expected_version=tested.account.version,
            status=BillingProviderAccountStatus.ACTIVE,
        )

    with pytest.raises(DadoComercialInvalido, match="billing_route_unavailable"):
        app.resolver_rota(
            product_code="KORDENA",
            payment_method=BillingPaymentMethod.PIX,
            environment=BillingEnvironment.PRODUCTION,
        )


def test_routing_rejects_environment_method_and_duplicates() -> None:
    provider = FakeConfigProvider("PROVIDER_ALPHA")
    _, _, app = _infra(provider)
    sandbox = _test_and_activate(
        app,
        _create_account(
            app,
            key="sandbox-alpha",
            provider_code="PROVIDER_ALPHA",
            secret_ref="mapping:alpha",
            environment=BillingEnvironment.SANDBOX,
            methods=(BillingPaymentMethod.PIX,),
        ),
    )

    with pytest.raises(DadoComercialInvalido, match="environment_mismatch"):
        app.criar_routing_policy(
            contexto=_context(),
            idempotency_key="route-bad-env",
            product_code="KORDENA",
            payment_method=BillingPaymentMethod.PIX,
            environment=BillingEnvironment.PRODUCTION,
            primary_provider_account_id=sandbox.provider_account_id,
        )

    with pytest.raises(DadoComercialInvalido, match="account_duplicate"):
        app.criar_routing_policy(
            contexto=_context(),
            idempotency_key="route-dup",
            product_code="KORDENA",
            payment_method=BillingPaymentMethod.PIX,
            environment=BillingEnvironment.SANDBOX,
            primary_provider_account_id=sandbox.provider_account_id,
            fallback_provider_account_ids=(sandbox.provider_account_id,),
        )

    with pytest.raises(DadoComercialInvalido, match="payment_method_not_supported"):
        app.criar_routing_policy(
            contexto=_context(),
            idempotency_key="route-card",
            product_code="KORDENA",
            payment_method=BillingPaymentMethod.CARD,
            environment=BillingEnvironment.SANDBOX,
            primary_provider_account_id=sandbox.provider_account_id,
        )


def test_provider_account_idempotency_and_secret_value_never_persisted() -> None:
    provider = FakeConfigProvider("PROVIDER_ALPHA")
    _, factory, app = _infra(provider)
    first = _create_account(
        app,
        key="idem-alpha",
        provider_code="PROVIDER_ALPHA",
        secret_ref="mapping:alpha",
    )
    retry = _create_account(
        app,
        key="idem-alpha",
        provider_code="PROVIDER_ALPHA",
        secret_ref="mapping:alpha",
    )
    assert retry.provider_account_id == first.provider_account_id

    with pytest.raises(
        ConflitoIdempotenciaComercial,
        match="idempotency_payload_conflict",
    ):
        app.criar_provider_account(
            contexto=_context(),
            idempotency_key="idem-alpha",
            provider_code="PROVIDER_BETA",
            display_name="Outra conta",
            legal_entity_ref=None,
            environment=BillingEnvironment.PRODUCTION,
            credential_secret_reference="mapping:beta",
            supported_payment_methods=(BillingPaymentMethod.PIX,),
            supports_recurring=False,
            supports_webhooks=False,
            priority=20,
        )

    with factory() as session:
        rows = session.scalars(select(FMBillingProviderAccountORM)).all()
        assert rows
        persisted = "\n".join(
            str(row.credential_secret_reference) for row in rows
        )
    assert "definitely-fake-secret" not in persisted
    assert "mapping:alpha" in persisted
