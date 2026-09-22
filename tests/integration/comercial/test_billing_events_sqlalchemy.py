from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.commercial_billing import BillingProviderAdapterRegistryV1
from application.commercial_billing_events import AplicacaoBillingEventsV1
from core.comercial.billing import (
    BillingCallContext,
    BillingTimeout,
    BillingTransaction,
    WebhookVerificationResult,
)
from core.comercial.billing_config import (
    BillingConnectionTestStatus,
    BillingEnvironment,
    BillingProviderAccountStatus,
)
from core.comercial.billing_events import (
    BillingCanonicalEventType,
    BillingReconciliationStatus,
    BillingWebhookInboxStatus,
    NormalizedBillingEvent,
)
from core.comercial.erros import ConflitoIdempotenciaComercial
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import ReferenceSecretStore, SecretValue
from infra.comercial.billing_config_orm import FMBillingProviderAccountORM
from infra.comercial.billing_events_orm import (
    FMBillingReconciliationRunORM,
    FMBillingTransactionORM,
    FMBillingWebhookInboxORM,
)
from infra.comercial.subscription_orm import FMCommercialSubscriptionORM
from migrations.runner import run_migrations


NOW = datetime(2026, 9, 22, 21, 45, tzinfo=timezone.utc)
ACCOUNT_ID = "billing-provider-account-test"
SUBSCRIPTION_ID = "subscription-kca10-test"


class FakeBillingProviderKCA10:
    provider_code = "PROVIDER_TEST"

    def __init__(self) -> None:
        self.verify_timeout = False
        self.fetch_result = BillingTransaction(
            provider_code=self.provider_code,
            external_transaction_ref="tx-default",
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
        assert credential.reveal() == "fake-kca10-secret"
        if self.verify_timeout:
            raise BillingTimeout("fake-timeout")
        data = json.loads(payload.decode("utf-8"))
        return WebhookVerificationResult(
            valid=headers.get("x-fake-signature") == "valid",
            event_id=str(data["id"]),
            event_type=str(data.get("type", "fake.event")),
        )

    def normalize_webhook(
        self,
        *,
        payload: bytes,
        verification: WebhookVerificationResult,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> NormalizedBillingEvent:
        assert credential.reveal() == "fake-kca10-secret"
        data = json.loads(payload.decode("utf-8"))
        return NormalizedBillingEvent(
            provider_code=self.provider_code,
            external_event_id=verification.event_id or str(data["id"]),
            canonical_event_type=BillingCanonicalEventType(str(data["canonical"])),
            occurred_at=datetime.fromisoformat(str(data["occurred_at"])),
            provider_sequence=(
                int(data["sequence"]) if data.get("sequence") is not None else None
            ),
            external_subscription_ref=data.get("subscription_ref"),
            external_transaction_ref=data.get("transaction_ref"),
            amount=(
                Decimal(str(data["amount"])) if data.get("amount") is not None else None
            ),
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
            metadata_safe={"source": "fake-kca10"},
        )

    def fetch_transaction(
        self,
        *,
        external_transaction_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingTransaction:
        assert credential.reveal() == "fake-kca10-secret"
        return BillingTransaction(
            provider_code=self.fetch_result.provider_code,
            external_transaction_ref=external_transaction_ref,
            status=self.fetch_result.status,
            amount=self.fetch_result.amount,
            currency=self.fetch_result.currency,
        )


class FakeSubscriptionApplication:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []

    def suspender(
        self,
        *,
        contexto,
        subscription_id: str,
        expected_version: int,
        motivo: str,
    ):
        self.calls.append(("suspender", subscription_id, expected_version))
        return None


def _context() -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="kca10-test",
        motivo="KCA-10 integration test",
        tenant_id="fm-commercial-platform",
        unidade_id="billing",
        correlation_id="corr-kca10",
        solicitado_em=NOW,
    )


def _infra(*, max_attempts: int = 5):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    provider = FakeBillingProviderKCA10()
    registry = BillingProviderAdapterRegistryV1((provider,))
    store = ReferenceSecretStore(
        mapping={"billing_kca10": "fake-kca10-secret"}
    )
    with factory() as session, session.begin():
        session.add(
            FMBillingProviderAccountORM(
                provider_account_id=ACCOUNT_ID,
                provider_code=provider.provider_code,
                display_name="Provider Test",
                legal_entity_ref=None,
                environment=BillingEnvironment.SANDBOX.value,
                status=BillingProviderAccountStatus.ACTIVE.value,
                credential_secret_reference="mapping:billing_kca10",
                supported_payment_methods=["pix", "card"],
                supports_recurring=True,
                supports_webhooks=True,
                priority=10,
                last_tested_at=NOW,
                last_test_status=BillingConnectionTestStatus.PASS.value,
                correlation_id="corr-provider",
                created_by="test",
                updated_by="test",
                version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    app = AplicacaoBillingEventsV1(
        factory,
        adapter_registry=registry,
        fallback_secret_store=store,
        max_attempts=max_attempts,
        retry_base_seconds=1,
    )
    return engine, factory, provider, app


def _payload(
    *,
    event_id: str,
    canonical: BillingCanonicalEventType,
    sequence: int,
    transaction_ref: str | None = None,
    subscription_ref: str | None = None,
    amount: str | None = None,
    occurred_at: datetime = NOW,
) -> bytes:
    data = {
        "id": event_id,
        "type": f"fake.{canonical.value}",
        "canonical": canonical.value,
        "occurred_at": occurred_at.isoformat(),
        "sequence": sequence,
        "transaction_ref": transaction_ref,
        "subscription_ref": subscription_ref,
        "amount": amount,
        "currency": "BRL" if amount is not None else None,
    }
    return json.dumps(data, sort_keys=True).encode("utf-8")


def _receive(app: AplicacaoBillingEventsV1, payload: bytes, *, valid: bool = True):
    return app.receber_webhook(
        contexto=_context(),
        provider_account_id=ACCOUNT_ID,
        payload=payload,
        headers={"x-fake-signature": "valid" if valid else "forged"},
    )


def _insert_subscription(factory) -> None:
    with factory() as session, session.begin():
        session.add(
            FMCommercialSubscriptionORM(
                subscription_id=SUBSCRIPTION_ID,
                fm_customer_id="customer-kca10",
                product_account_id="product-account-kca10",
                tenant_id="tenant-kca10",
                plan_code="KORDENA_PLAN_A",
                plan_version_id="plan-version-kca10",
                price_id="price-kca10",
                currency="BRL",
                billing_period="monthly",
                contracted_amount=Decimal("99.90"),
                status="active",
                current_period_start=NOW,
                current_period_end=NOW + timedelta(days=30),
                cancel_at_period_end=False,
                canceled_at=None,
                activated_at=NOW,
                suspended_at=None,
                version=1,
                correlation_id="corr-subscription",
                created_at=NOW,
                updated_at=NOW,
            )
        )


def test_forged_signature_is_durable_rejected_without_financial_effect() -> None:
    _, factory, _, app = _infra()
    row = _receive(
        app,
        _payload(
            event_id="evt-forged",
            canonical=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
            sequence=1,
            transaction_ref="tx-forged",
            amount="10.00",
        ),
        valid=False,
    )
    assert row.status == BillingWebhookInboxStatus.REJECTED.value
    assert row.signature_valid is False

    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FMBillingTransactionORM)) == 0
        assert session.scalar(select(func.count()).select_from(FMBillingWebhookInboxORM)) == 1


def test_duplicate_and_provider_resend_are_idempotent() -> None:
    _, factory, _, app = _infra()
    payload = _payload(
        event_id="evt-dup",
        canonical=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
        sequence=1,
        transaction_ref="tx-dup",
        amount="99.90",
    )
    first = _receive(app, payload)
    second = _receive(app, payload)

    assert first.inbox_id == second.inbox_id
    assert second.status == BillingWebhookInboxStatus.PROCESSED.value
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FMBillingWebhookInboxORM)) == 1
        assert session.scalar(select(func.count()).select_from(FMBillingTransactionORM)) == 1


def test_same_event_id_with_different_body_fails_closed() -> None:
    _, _, _, app = _infra()
    first = _payload(
        event_id="evt-replay-conflict",
        canonical=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
        sequence=1,
        transaction_ref="tx-replay",
        amount="10.00",
    )
    second = _payload(
        event_id="evt-replay-conflict",
        canonical=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
        sequence=1,
        transaction_ref="tx-replay",
        amount="11.00",
    )
    _receive(app, first)
    with pytest.raises(
        ConflitoIdempotenciaComercial,
        match="replay_body_conflict",
    ):
        _receive(app, second)


def test_out_of_order_event_does_not_regress_ledger() -> None:
    _, factory, _, app = _infra()
    newer = _payload(
        event_id="evt-seq-2",
        canonical=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
        sequence=2,
        transaction_ref="tx-order",
        amount="55.00",
        occurred_at=NOW + timedelta(seconds=2),
    )
    older = _payload(
        event_id="evt-seq-1",
        canonical=BillingCanonicalEventType.PAYMENT_FAILED,
        sequence=1,
        transaction_ref="tx-order",
        amount="55.00",
        occurred_at=NOW + timedelta(seconds=1),
    )
    assert _receive(app, newer).status == BillingWebhookInboxStatus.PROCESSED.value
    ignored = _receive(app, older)
    assert ignored.status == BillingWebhookInboxStatus.IGNORED_OUT_OF_ORDER.value

    with factory() as session:
        tx = session.scalar(
            select(FMBillingTransactionORM).where(
                FMBillingTransactionORM.external_transaction_ref == "tx-order"
            )
        )
        assert tx is not None
        assert tx.status == "succeeded"
        assert tx.last_external_event_id == "evt-seq-2"


def test_verification_timeout_has_no_partial_financial_state() -> None:
    _, factory, provider, app = _infra()
    provider.verify_timeout = True
    with pytest.raises(BillingTimeout):
        _receive(
            app,
            _payload(
                event_id="evt-timeout",
                canonical=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
                sequence=1,
                transaction_ref="tx-timeout",
                amount="1.00",
            ),
        )
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(FMBillingWebhookInboxORM)) == 0
        assert session.scalar(select(func.count()).select_from(FMBillingTransactionORM)) == 0


def test_retry_processes_after_subscription_binding_appears() -> None:
    _, factory, _, app = _infra()
    fake_subscription = FakeSubscriptionApplication()
    app._subscription = fake_subscription  # noqa: SLF001
    payload = _payload(
        event_id="evt-retry",
        canonical=BillingCanonicalEventType.SUBSCRIPTION_SUSPENDED,
        sequence=1,
        subscription_ref="external-sub-retry",
    )
    first = _receive(app, payload)
    assert first.status == BillingWebhookInboxStatus.FAILED_RETRYABLE.value
    assert first.attempts == 1

    _insert_subscription(factory)
    app.registrar_subscription_binding(
        contexto=_context(),
        provider_account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        external_subscription_ref="external-sub-retry",
    )
    processed = app.processar_retries(
        contexto=_context(),
        now=NOW + timedelta(minutes=10),
    )
    assert processed == (first.inbox_id,)
    current = app.obter_inbox(inbox_id=first.inbox_id)
    assert current.status == BillingWebhookInboxStatus.PROCESSED.value
    assert fake_subscription.calls == [("suspender", SUBSCRIPTION_ID, 1)]


def test_retry_exhaustion_goes_dlq_and_controlled_replay_rechecks_binding() -> None:
    _, factory, _, app = _infra(max_attempts=2)
    fake_subscription = FakeSubscriptionApplication()
    app._subscription = fake_subscription  # noqa: SLF001
    payload = _payload(
        event_id="evt-dlq",
        canonical=BillingCanonicalEventType.SUBSCRIPTION_SUSPENDED,
        sequence=1,
        subscription_ref="external-sub-dlq",
    )
    first = _receive(app, payload)
    assert first.status == BillingWebhookInboxStatus.FAILED_RETRYABLE.value

    dead = app.processar_inbox(contexto=_context(), inbox_id=first.inbox_id)
    assert dead.status == BillingWebhookInboxStatus.DEAD_LETTER.value
    assert dead.attempts == 2

    _insert_subscription(factory)
    app.registrar_subscription_binding(
        contexto=_context(),
        provider_account_id=ACCOUNT_ID,
        subscription_id=SUBSCRIPTION_ID,
        external_subscription_ref="external-sub-dlq",
    )
    replayed = app.reprocessar_dead_letter(
        contexto=_context(),
        inbox_id=dead.inbox_id,
        expected_version=dead.version,
    )
    assert replayed.status == BillingWebhookInboxStatus.PROCESSED.value
    assert fake_subscription.calls == [("suspender", SUBSCRIPTION_ID, 1)]


def test_reconciliation_repairs_internal_transaction_state() -> None:
    _, factory, provider, app = _infra()
    _receive(
        app,
        _payload(
            event_id="evt-reconcile",
            canonical=BillingCanonicalEventType.PAYMENT_FAILED,
            sequence=1,
            transaction_ref="tx-reconcile",
            amount="99.90",
        ),
    )
    with factory() as session:
        tx = session.scalar(
            select(FMBillingTransactionORM).where(
                FMBillingTransactionORM.external_transaction_ref == "tx-reconcile"
            )
        )
        assert tx is not None
        transaction_id = tx.billing_transaction_id
        assert tx.status == "failed"

    provider.fetch_result = BillingTransaction(
        provider_code=provider.provider_code,
        external_transaction_ref="tx-reconcile",
        status="succeeded",
        amount=Decimal("99.90"),
        currency="BRL",
    )
    repaired = app.reconciliar_transacao(
        contexto=_context(),
        billing_transaction_id=transaction_id,
    )
    assert repaired.status == "succeeded"
    assert (
        repaired.reconciliation_status
        == BillingReconciliationStatus.REPAIRED.value
    )
    with factory() as session:
        run = session.scalar(select(FMBillingReconciliationRunORM))
        assert run is not None
        assert run.status == "repaired"
        assert run.previous_status == "failed"
        assert run.final_status == "succeeded"
