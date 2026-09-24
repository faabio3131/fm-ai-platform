"""KCA-16 full commercial backend E2E on real ephemeral PostgreSQL.

Journey:
signup -> email verification -> provisioning -> trial -> login -> operations ->
trial expiry -> paywall -> plan -> sandbox checkout -> payment webhook ->
subscription active -> entitlement restored -> FMCC/observability/audit.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from application.commercial_billing import BillingProviderAdapterRegistryV1
from application.commercial_billing_config import AplicacaoBillingConfigurationV1
from application.commercial_billing_events import AplicacaoBillingEventsV1
from application.commercial_catalog import AplicacaoCatalogoComercialV1
from application.commercial_trial import AplicacaoTrialComercialV1
from core.comercial.billing import (
    BillingCallContext,
    BillingConnectionTestResult,
    BillingCustomerReference,
    BillingCustomerRequest,
    BillingSubscriptionChangeRequest,
    BillingSubscriptionRequest,
    BillingTransaction,
    CheckoutRequest,
    CheckoutResult,
    ProviderSubscriptionReference,
    WebhookVerificationResult,
)
from core.comercial.billing_config import (
    BillingEnvironment,
    BillingPaymentMethod,
    BillingProviderAccountStatus,
)
from core.comercial.billing_events import (
    BillingCanonicalEventType,
    NormalizedBillingEvent,
)
from core.comercial.catalogo import PoliticaMudancaPreco
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore, SecretValue
from http_api.frontend_app import build_frontend_http_app
from infra.comercial.billing_events_orm import FMBillingTransactionORM
from infra.comercial.catalogo_orm import FMCommercialPlanORM
from infra.comercial.provisioning_orm import FMCommercialProvisioningSagaORM
from infra.comercial.signup_orm import FMPublicSignupIntentORM
from infra.comercial.subscription_orm import FMCommercialSubscriptionORM
from infra.comercial.trial_orm import FMCommercialTrialORM
from migrations.runner import run_migrations

EMAIL = "kca16-customer@example.test"
PASSWORD = "KCA16-Customer-Password-2026!"
PLAN_CODE = "KORDENA_PLAN_A"
PROVIDER_CODE = "KCA16_SANDBOX"
ORIGIN = "https://kca16.local"


@dataclass
class CaptureDispatcher:
    sent: list[tuple[str, str, str]] = field(default_factory=list)

    def send_verification(self, *, signup_id: str, email: str, token: str) -> None:
        self.sent.append((signup_id, email, token))


class SandboxBillingProvider:
    provider_code = PROVIDER_CODE

    def _credential(self, credential: SecretValue) -> None:
        assert credential.reveal() == "kca16-sandbox-secret"

    def test_connection(
        self,
        *,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingConnectionTestResult:
        self._credential(credential)
        assert context.idempotency_key
        return BillingConnectionTestResult(
            ok=True,
            provider_code=self.provider_code,
            detail_code="sandbox_connection_ok",
        )

    def create_customer(
        self,
        *,
        request: BillingCustomerRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingCustomerReference:
        self._credential(credential)
        return BillingCustomerReference(
            provider_code=self.provider_code,
            external_customer_ref=f"cust-{request.fm_customer_id}",
        )

    def create_checkout(
        self,
        *,
        request: CheckoutRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> CheckoutResult:
        self._credential(credential)
        assert request.subscription_id
        return CheckoutResult(
            provider_code=self.provider_code,
            external_checkout_ref=f"checkout-{request.subscription_id}",
            checkout_url=f"{ORIGIN}/sandbox-checkout/{request.subscription_id}",
            external_subscription_ref=f"sub-{request.subscription_id}",
            external_customer_ref=f"cust-{request.fm_customer_id}",
        )

    def create_subscription(
        self,
        *,
        request: BillingSubscriptionRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        self._credential(credential)
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=f"sub-{request.product_account_id}",
            external_customer_ref=request.external_customer_ref,
        )

    def cancel_subscription(
        self,
        *,
        external_subscription_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        self._credential(credential)
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=external_subscription_ref,
            external_customer_ref="kca16-customer",
        )

    def change_subscription(
        self,
        *,
        request: BillingSubscriptionChangeRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        self._credential(credential)
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=request.external_subscription_ref,
            external_customer_ref="kca16-customer",
        )

    def fetch_transaction(
        self,
        *,
        external_transaction_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingTransaction:
        self._credential(credential)
        return BillingTransaction(
            provider_code=self.provider_code,
            external_transaction_ref=external_transaction_ref,
            status="succeeded",
            amount=Decimal("99.90"),
            currency="BRL",
        )

    def verify_webhook(
        self,
        *,
        payload: bytes,
        headers,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> WebhookVerificationResult:
        self._credential(credential)
        data = json.loads(payload.decode("utf-8"))
        return WebhookVerificationResult(
            valid=headers.get("x-kca16-signature") == "valid",
            event_id=str(data["id"]),
            event_type=str(data["canonical"]),
        )

    def normalize_webhook(
        self,
        *,
        payload: bytes,
        verification: WebhookVerificationResult,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> NormalizedBillingEvent:
        self._credential(credential)
        data = json.loads(payload.decode("utf-8"))
        return NormalizedBillingEvent(
            provider_code=self.provider_code,
            external_event_id=str(data["id"]),
            canonical_event_type=BillingCanonicalEventType(str(data["canonical"])),
            occurred_at=datetime.fromisoformat(str(data["occurred_at"])),
            provider_sequence=int(data["sequence"]),
            external_subscription_ref=data.get("subscription_ref"),
            external_transaction_ref=data.get("transaction_ref"),
            amount=Decimal(str(data["amount"])) if data.get("amount") else None,
            currency=data.get("currency"),
            period_start=(
                datetime.fromisoformat(str(data["period_start"]))
                if data.get("period_start")
                else None
            ),
            period_end=(
                datetime.fromisoformat(str(data["period_end"]))
                if data.get("period_end")
                else None
            ),
            metadata_safe={"source": "kca16-sandbox"},
        )


def _admin_context() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="fm-internal",
        unidade_id="fm-hq",
        usuario_id="kca16-director",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="kca16-admin",
        solicitado_em=datetime.now(timezone.utc),
        origem="kca16_full_e2e",
        unidades_permitidas=frozenset({"fm-hq"}),
        identity_user_id="kca16-director-global",
        membership_id="kca16-director-membership",
        product_code="KORDENA",
    )


def _publish_plan(factory):
    now = datetime.now(timezone.utc)
    app = AplicacaoCatalogoComercialV1(factory)
    ctx = _admin_context()
    with factory() as session:
        plan = session.scalar(
            select(FMCommercialPlanORM).where(
                FMCommercialPlanORM.plan_code == PLAN_CODE
            )
        )
        assert plan is not None
        plan_version = int(plan.version)

    version = app.criar_versao_plano(
        contexto=ctx,
        idempotency_key="kca16-plan-version",
        plan_code=PLAN_CODE,
        display_name="Kordena KCA-16",
        description="Plano sandbox para a jornada comercial final",
        trial_eligible=True,
        marketing_badge="KCA16",
        metadata={"e2e": True},
        entitlements=(),
        change_reason="KCA-16 full commercial E2E",
    )
    version = app.validar_versao_plano(
        contexto=ctx,
        plan_version_id=version.plan_version_id,
        change_reason="KCA-16 validate plan",
    )
    version = app.publicar_versao_plano(
        contexto=ctx,
        idempotency_key="kca16-plan-publish",
        plan_version_id=version.plan_version_id,
        expected_plan_version=plan_version,
        effective_from=now - timedelta(minutes=10),
        change_reason="KCA-16 publish plan",
    )
    with factory() as session:
        plan = session.scalar(
            select(FMCommercialPlanORM).where(
                FMCommercialPlanORM.plan_code == PLAN_CODE
            )
        )
        assert plan is not None
        price_expected_version = int(plan.version)

    price = app.criar_preco(
        contexto=ctx,
        idempotency_key="kca16-price",
        plan_version_id=version.plan_version_id,
        currency="BRL",
        billing_period="monthly",
        amount=Decimal("99.90"),
        change_policy=PoliticaMudancaPreco.NEW_CUSTOMERS_ONLY,
        change_reason="KCA-16 sandbox price",
    )
    price = app.validar_preco(
        contexto=ctx,
        price_id=price.price_id,
        change_reason="KCA-16 validate price",
    )
    price = app.publicar_preco(
        contexto=ctx,
        idempotency_key="kca16-price-publish",
        price_id=price.price_id,
        expected_plan_version=price_expected_version,
        effective_from=now - timedelta(minutes=5),
        change_reason="KCA-16 publish price",
    )
    return version, price


def _configure_billing(factory, registry, store):
    app = AplicacaoBillingConfigurationV1(
        factory,
        adapter_registry=registry,
        secret_store=store,
    )
    account = app.criar_provider_account(
        contexto=_admin_context(),
        idempotency_key="kca16-provider-account",
        provider_code=PROVIDER_CODE,
        display_name="KCA-16 Sandbox",
        legal_entity_ref=None,
        environment=BillingEnvironment.SANDBOX,
        credential_secret_reference="mapping:billing",
        supported_payment_methods=(BillingPaymentMethod.PIX,),
        supports_recurring=True,
        supports_webhooks=True,
        priority=1,
    )
    tested = app.testar_conexao(
        contexto=_admin_context(),
        provider_account_id=account.provider_account_id,
        expected_version=account.version,
    )
    assert tested.ok is True
    account = app.transicionar_provider_account(
        contexto=_admin_context(),
        provider_account_id=account.provider_account_id,
        expected_version=tested.account.version,
        status=BillingProviderAccountStatus.ACTIVE,
    )
    app.criar_routing_policy(
        contexto=_admin_context(),
        idempotency_key="kca16-route-pix",
        product_code="KORDENA",
        payment_method=BillingPaymentMethod.PIX,
        environment=BillingEnvironment.SANDBOX,
        primary_provider_account_id=account.provider_account_id,
        requires_recurring=True,
        requires_webhooks=True,
    )
    return account


def _webhook(
    client: TestClient,
    provider_account_id: str,
    payload: dict[str, object],
):
    return client.post(
        f"/v1/commercial/billing/webhooks/{provider_account_id}",
        json=payload,
        headers={"X-KCA16-Signature": "valid"},
    )


def run(output: Path) -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("KCA-16 must run outside FM_AI_TEST_MODE")
    database_url = os.environ["DATABASE_URL"].strip()
    if not database_url.startswith("postgresql"):
        raise RuntimeError("KCA-16 requires PostgreSQL")

    os.environ.setdefault("FM_AI_SECRET_MASTER_KEY", Fernet.generate_key().decode())
    engine = create_engine(database_url, future=True)
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    plan_version, price = _publish_plan(factory)
    provider = SandboxBillingProvider()
    registry = BillingProviderAdapterRegistryV1((provider,))
    signup_key = Fernet.generate_key().decode("ascii")
    store = ReferenceSecretStore(
        mapping={"signup": signup_key, "billing": "kca16-sandbox-secret"}
    )
    provider_account = _configure_billing(factory, registry, store)
    dispatcher = CaptureDispatcher()

    settings = RuntimeSettings(
        environment=RuntimeEnvironment.STAGING,
        database_url=database_url,
        tenant_id="kca16-bootstrap",
        unidade_id="kca16-bootstrap",
        commercial_access_gate_enabled=True,
        fmcc_control_plane_token=os.environ["FM_AI_FMCC_CONTROL_PLANE_TOKEN"],
    ).validate()
    app = build_frontend_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
        secret_store=store,
        public_signup_enabled=True,
        signup_verification_dispatcher=dispatcher,
        signup_credential_secret_reference="mapping:signup",
        commercial_access_gate_enabled=True,
        commercial_billing_adapter_registry=registry,
    )
    client = TestClient(app, base_url=ORIGIN)

    signup = client.post(
        "/v1/public/signup",
        json={
            "owner_name": "Cliente KCA-16",
            "email": EMAIL,
            "password": PASSWORD,
            "phone": "+5511999999999",
            "establishment_name": "Restaurante KCA-16",
            "segment": "restaurante",
            "terms_accepted": True,
            "consents": {"marketing": False},
        },
    )
    assert signup.status_code == 202, signup.text
    signup_id = signup.json()["signup_id"]
    assert len(dispatcher.sent) == 1
    sent_signup, sent_email, token = dispatcher.sent[0]
    assert sent_signup == signup_id
    assert sent_email == EMAIL

    verified = client.post(
        f"/v1/public/signup/{signup_id}/verify-email",
        json={"token": token},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["ready"] is True

    with factory() as session:
        signup_row = session.get(FMPublicSignupIntentORM, signup_id)
        assert signup_row is not None and signup_row.provisioning_id
        saga = session.get(
            FMCommercialProvisioningSagaORM,
            signup_row.provisioning_id,
        )
        assert saga is not None
        assert saga.status == "ready"
        assert saga.fm_customer_id
        assert saga.product_account_id
        tenant_id = saga.tenant_id
        unit_id = saga.unidade_id
        product_account_id = saga.product_account_id
        trial = session.scalar(
            select(FMCommercialTrialORM).where(
                FMCommercialTrialORM.product_account_id == product_account_id
            )
        )
        assert trial is not None
        trial_id = trial.trial_id
        trial_ends_at = trial.ends_at
        assert trial_ends_at is not None

    login = client.post("/v1/auth/login", json={"email": EMAIL, "senha": PASSWORD})
    assert login.status_code == 200, login.text
    me = client.get("/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["tenant_id"] == tenant_id
    assert me.json()["unidade_ativa_id"] == unit_id

    initial_access = client.get("/v1/commercial/access")
    assert initial_access.status_code == 200
    assert initial_access.json()["operational_allowed"] is True
    assert initial_access.json()["access_mode"] == "full"

    onboarding = client.get("/v1/admin/empresa")
    assert onboarding.status_code == 200, onboarding.text

    operational = client.get("/v1/pdv/produtos")
    assert operational.status_code == 200, operational.text

    expired = AplicacaoTrialComercialV1(factory).expirar(
        contexto=ContextoExecucao.sistema(
            identidade="kca16-expiration",
            motivo="KCA-16 trial boundary",
            tenant_id=tenant_id,
            unidade_id=unit_id,
            correlation_id="kca16-expiration",
            solicitado_em=trial_ends_at,
        ),
        trial_id=trial_id,
        agora=trial_ends_at,
    )
    assert expired.status.value == "expired"

    blocked_access = client.get("/v1/commercial/access")
    assert blocked_access.status_code == 200
    assert blocked_access.json()["operational_allowed"] is False
    assert blocked_access.json()["access_mode"] == "billing_only"
    assert client.get("/v1/pdv/produtos").status_code == 402

    plans = client.get("/v1/commercial/plans")
    assert plans.status_code == 200
    offer = next(item for item in plans.json() if item["plan_code"] == PLAN_CODE)
    assert offer["plan_version_id"] == plan_version.plan_version_id
    selected_price = next(
        item for item in offer["prices"] if item["price_id"] == price.price_id
    )

    checkout = client.post(
        "/v1/commercial/checkout",
        headers={
            "Origin": ORIGIN,
            "Idempotency-Key": "kca16-checkout",
        },
        json={
            "plan_code": PLAN_CODE,
            "plan_version_id": plan_version.plan_version_id,
            "price_id": selected_price["price_id"],
            "payment_method": "pix",
            "success_url": f"{ORIGIN}/?commercial_checkout=success",
            "cancel_url": f"{ORIGIN}/?commercial_checkout=cancel",
        },
    )
    assert checkout.status_code == 200, checkout.text
    checkout_body = checkout.json()
    assert checkout_body["subscription_status"] == "pending"
    subscription_id = checkout_body["subscription_id"]
    external_subscription_ref = f"sub-{subscription_id}"

    now = datetime.now(timezone.utc)
    payment = _webhook(
        client,
        provider_account.provider_account_id,
        {
            "id": "evt-kca16-payment",
            "canonical": "payment_succeeded",
            "occurred_at": now.isoformat(),
            "sequence": 1,
            "subscription_ref": external_subscription_ref,
            "transaction_ref": "tx-kca16-payment",
            "amount": "99.90",
            "currency": "BRL",
        },
    )
    assert payment.status_code == 202, payment.text

    activated = _webhook(
        client,
        provider_account.provider_account_id,
        {
            "id": "evt-kca16-sub-active",
            "canonical": "subscription_active",
            "occurred_at": (now + timedelta(seconds=1)).isoformat(),
            "sequence": 2,
            "subscription_ref": external_subscription_ref,
            "period_start": now.isoformat(),
            "period_end": (now + timedelta(days=30)).isoformat(),
        },
    )
    assert activated.status_code == 202, activated.text

    subscription = client.get("/v1/commercial/subscription")
    assert subscription.status_code == 200
    assert subscription.json()["subscription"]["status"] == "active"

    restored = client.get("/v1/commercial/access")
    assert restored.status_code == 200
    assert restored.json()["operational_allowed"] is True
    assert restored.json()["access_mode"] == "full"
    assert client.get("/v1/pdv/produtos").status_code == 200

    with factory() as session:
        tx = session.scalar(
            select(FMBillingTransactionORM).where(
                FMBillingTransactionORM.external_transaction_ref
                == "tx-kca16-payment"
            )
        )
        assert tx is not None
        transaction_id = tx.billing_transaction_id
        sub = session.get(FMCommercialSubscriptionORM, subscription_id)
        assert sub is not None and sub.status == "active"

    reconciled = AplicacaoBillingEventsV1(
        factory,
        adapter_registry=registry,
        fallback_secret_store=store,
    ).reconciliar_transacao(
        contexto=_admin_context(),
        billing_transaction_id=transaction_id,
    )
    assert reconciled.status == "succeeded"

    fmcc = client.get(
        "/v1/control-plane/fmcc/snapshot",
        headers={
            "Authorization": (
                f"Bearer {os.environ['FM_AI_FMCC_CONTROL_PLANE_TOKEN']}"
            )
        },
    )
    assert fmcc.status_code == 200, fmcc.text
    snapshot = fmcc.json()
    assert any(
        row["product_account_id"] == product_account_id
        for row in snapshot["product_accounts"]
    )
    assert snapshot["observability"]["metrics"]["subscription_active"]["value"] >= 1
    assert (
        snapshot["observability"]["metrics"]["payment_success"]["value"] >= 1
    )

    logout = client.post("/v1/auth/logout")
    assert logout.status_code == 200

    evidence = {
        "gate": "KCA-G16-BACKEND-E2E",
        "environment": "ephemeral_postgresql_staging",
        "fm_ai_test_mode": False,
        "journey": {
            "signup": "pass",
            "email_verification": "pass",
            "customer_product_account": "pass",
            "tenant_company_unit_membership": "pass",
            "trial_active": "pass",
            "entitlement_initial": "pass",
            "login": "pass",
            "onboarding_scope": "pass",
            "kordena_operations": "pass",
            "trial_expiration": "pass",
            "paywall_billing_only": "pass",
            "plan_selection": "pass",
            "sandbox_checkout": "pass",
            "payment_webhook": "pass",
            "subscription_active": "pass",
            "entitlement_restored": "pass",
            "kordena_access_restored": "pass",
            "reconciliation": "pass",
            "fmcc_updated": "pass",
            "observability_updated": "pass",
            "logout": "pass",
        },
        "billing_real_used": False,
        "provider": PROVIDER_CODE,
        "tenant_id": tenant_id,
        "product_account_id": product_account_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="evidence/kca16-full-commercial-e2e.json",
    )
    args = parser.parse_args()
    run(Path(args.output))


if __name__ == "__main__":
    main()
