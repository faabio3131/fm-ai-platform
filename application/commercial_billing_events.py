"""Webhook Inbox, Billing Ledger e Reconciliation provider-neutral — KCA-10."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from application.commercial_billing import (
    BillingGatewayV1,
    BillingProviderAdapterRegistryV1,
    BillingProviderBinding,
)
from application.commercial_subscription import AplicacaoSubscriptionComercialV1
from core.comercial.billing import (
    BillingCallContext,
    BillingProviderError,
    BillingTransaction,
)
from core.comercial.billing_config import BillingProviderAccountStatus
from core.comercial.billing_events import (
    BillingCanonicalEventType,
    BillingReconciliationStatus,
    BillingTransactionStatus,
    BillingTransactionType,
    BillingWebhookInboxStatus,
    NormalizedBillingEvent,
    is_out_of_order,
    transaction_status_for_event,
)
from core.comercial.erros import (
    ConflitoConcorrenciaComercial,
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
    TransicaoComercialInvalida,
)
from core.comercial.subscription import EstadoAssinatura
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import ReferenciaSegredoInvalida, SegredoAusente
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from infra.comercial.billing_config_sqlalchemy import RepositorioBillingConfigSQLAlchemy
from infra.comercial.billing_events_orm import (
    FMBillingEventCursorORM,
    FMBillingReconciliationRunORM,
    FMBillingSubscriptionBindingORM,
    FMBillingTransactionORM,
    FMBillingWebhookInboxORM,
)
from infra.comercial.billing_events_sqlalchemy import RepositorioBillingEventsSQLAlchemy
from infra.comercial.modelos_orm import CommercialAuditORM
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy
from infra.comercial.subscription_sqlalchemy import (
    RepositorioSubscriptionComercialSQLAlchemy,
)
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore


class BillingBindingPending(RuntimeError):
    pass


class BillingRetryableProcessingError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _actor(contexto: ContextoExecucao) -> str:
    return contexto.identity_user_id or contexto.usuario_id


def _body_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_code(value: str, *, fallback: str) -> str:
    code = value.strip()[:128]
    if (
        not code
        or not all(char.isalnum() or char in {"_", "-", ".", ":"} for char in code)
    ):
        return fallback
    return code


def _event_payload(event: NormalizedBillingEvent) -> dict[str, object]:
    return {
        "provider_code": event.provider_code,
        "external_event_id": event.external_event_id,
        "canonical_event_type": event.canonical_event_type.value,
        "occurred_at": event.occurred_at.isoformat(),
        "provider_sequence": event.provider_sequence,
        "external_subscription_ref": event.external_subscription_ref,
        "external_transaction_ref": event.external_transaction_ref,
        "transaction_type": (
            event.transaction_type.value if event.transaction_type else None
        ),
        "transaction_status": (
            event.transaction_status.value if event.transaction_status else None
        ),
        "amount": str(event.amount) if event.amount is not None else None,
        "currency": event.currency,
        "period_start": (
            event.period_start.isoformat() if event.period_start else None
        ),
        "period_end": event.period_end.isoformat() if event.period_end else None,
        "metadata_safe": dict(event.metadata_safe or {}),
    }


def _event_from_payload(payload: dict[str, object]) -> NormalizedBillingEvent:
    def dt(name: str) -> datetime | None:
        raw = payload.get(name)
        return datetime.fromisoformat(str(raw)) if raw else None

    amount_raw = payload.get("amount")
    transaction_type = payload.get("transaction_type")
    transaction_status = payload.get("transaction_status")
    return NormalizedBillingEvent(
        provider_code=str(payload["provider_code"]),
        external_event_id=str(payload["external_event_id"]),
        canonical_event_type=BillingCanonicalEventType(
            str(payload["canonical_event_type"])
        ),
        occurred_at=datetime.fromisoformat(str(payload["occurred_at"])),
        provider_sequence=(
            int(payload["provider_sequence"])
            if payload.get("provider_sequence") is not None
            else None
        ),
        external_subscription_ref=(
            str(payload["external_subscription_ref"])
            if payload.get("external_subscription_ref")
            else None
        ),
        external_transaction_ref=(
            str(payload["external_transaction_ref"])
            if payload.get("external_transaction_ref")
            else None
        ),
        transaction_type=(
            BillingTransactionType(str(transaction_type))
            if transaction_type
            else None
        ),
        transaction_status=(
            BillingTransactionStatus(str(transaction_status))
            if transaction_status
            else None
        ),
        amount=Decimal(str(amount_raw)) if amount_raw is not None else None,
        currency=str(payload["currency"]) if payload.get("currency") else None,
        period_start=dt("period_start"),
        period_end=dt("period_end"),
        metadata_safe=dict(payload.get("metadata_safe") or {}),
    )


def _canonical_provider_transaction_status(value: str) -> BillingTransactionStatus:
    normalized = value.strip().casefold()
    try:
        return BillingTransactionStatus(normalized)
    except ValueError as exc:
        raise DadoComercialInvalido(
            "billing_reconciliation_status_nao_canonico"
        ) from exc


class AplicacaoBillingEventsV1:
    def __init__(
        self,
        session_factory,
        *,
        adapter_registry: BillingProviderAdapterRegistryV1,
        fallback_secret_store: SecretStore | None = None,
        max_attempts: int = 5,
        retry_base_seconds: int = 5,
    ) -> None:
        if max_attempts < 1 or max_attempts > 20:
            raise ValueError("billing_max_attempts_invalido")
        if retry_base_seconds < 1 or retry_base_seconds > 3600:
            raise ValueError("billing_retry_base_seconds_invalido")
        self._session_factory = session_factory
        self._adapter_registry = adapter_registry
        self._fallback_secret_store = (
            fallback_secret_store or ReferenceSecretStore()
        )
        self._max_attempts = max_attempts
        self._retry_base_seconds = retry_base_seconds
        self._subscription = AplicacaoSubscriptionComercialV1(session_factory)

    @staticmethod
    def _audit(
        *,
        contexto: ContextoExecucao,
        action: str,
        aggregate_type: str,
        aggregate_id: str,
        result: str,
        reason: str,
        metadata_safe: dict[str, object],
        instante: datetime,
    ) -> CommercialAuditORM:
        return CommercialAuditORM(
            audit_id=str(uuid4()),
            actor_user_id=_actor(contexto),
            action=action,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            result=result,
            reason=reason[:255],
            correlation_id=contexto.correlation_id,
            causation_id=contexto.causation_id,
            metadata_safe=metadata_safe,
            timestamp=instante,
        )

    def _gateway_in_session(
        self,
        *,
        session,
        provider_account_id: str,
        require_webhooks: bool,
    ) -> tuple[object, BillingGatewayV1]:
        account = RepositorioBillingConfigSQLAlchemy(
            session
        ).obter_provider_account(provider_account_id.strip())
        if account is None:
            raise RegistroComercialNaoEncontrado(
                "billing_provider_account_not_found"
            )
        if account.status not in {
            BillingProviderAccountStatus.ACTIVE,
            BillingProviderAccountStatus.SUSPENDED,
        }:
            raise DadoComercialInvalido(
                "billing_provider_account_not_ready_for_events"
            )
        if require_webhooks and not account.supports_webhooks:
            raise DadoComercialInvalido(
                "billing_provider_account_webhooks_not_supported"
            )
        if not account.credential_secret_reference:
            raise DadoComercialInvalido("billing_credential_not_configured")
        provider = self._adapter_registry.resolve(account.provider_code)
        store: SecretStore
        if account.credential_secret_reference.startswith("vault:"):
            store = EncryptedSQLAlchemySecretStore(session)
        else:
            store = self._fallback_secret_store
        gateway = BillingGatewayV1(
            provider=provider,
            binding=BillingProviderBinding(
                provider_code=account.provider_code,
                credential_secret_reference=account.credential_secret_reference,
            ),
            secret_store=store,
        )
        return account, gateway

    def registrar_subscription_binding(
        self,
        *,
        contexto: ContextoExecucao,
        provider_account_id: str,
        subscription_id: str,
        external_subscription_ref: str,
        external_customer_ref: str | None = None,
    ) -> str:
        account_id = provider_account_id.strip()
        internal_id = subscription_id.strip()
        external_ref = external_subscription_ref.strip()
        if not internal_id or not external_ref:
            raise DadoComercialInvalido("billing_subscription_binding_invalido")
        instante = _now()
        try:
            with self._session_factory() as session, session.begin():
                account = RepositorioBillingConfigSQLAlchemy(
                    session
                ).obter_provider_account(account_id)
                if account is None:
                    raise RegistroComercialNaoEncontrado(
                        "billing_provider_account_not_found"
                    )
                subscription = RepositorioSubscriptionComercialSQLAlchemy(
                    session
                ).obter(internal_id)
                if subscription is None:
                    raise RegistroComercialNaoEncontrado(
                        "subscription_not_found"
                    )
                repo = RepositorioBillingEventsSQLAlchemy(session)
                by_external = repo.obter_binding_por_external(
                    provider_account_id=account_id,
                    external_subscription_ref=external_ref,
                )
                by_internal = repo.obter_binding_por_subscription(
                    provider_account_id=account_id,
                    subscription_id=internal_id,
                )
                if by_external is not None or by_internal is not None:
                    existing = by_external or by_internal
                    if (
                        existing is not None
                        and existing.subscription_id == internal_id
                        and existing.external_subscription_ref == external_ref
                    ):
                        return existing.billing_binding_id
                    raise RegistroComercialDuplicado(
                        "billing_subscription_binding_conflict"
                    )
                binding_id = str(uuid4())
                repo.adicionar_binding(
                    FMBillingSubscriptionBindingORM(
                        billing_binding_id=binding_id,
                        provider_account_id=account_id,
                        provider_code=account.provider_code,
                        subscription_id=internal_id,
                        external_subscription_ref=external_ref,
                        external_customer_ref=(
                            external_customer_ref.strip()
                            if external_customer_ref
                            else None
                        ),
                        version=1,
                        correlation_id=contexto.correlation_id,
                        created_at=instante,
                        updated_at=instante,
                    )
                )
                RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                    self._audit(
                        contexto=contexto,
                        action="commercial.billing.subscription_binding.create",
                        aggregate_type="billing_subscription_binding",
                        aggregate_id=binding_id,
                        result="success",
                        reason="KCA-10 external subscription binding",
                        metadata_safe={
                            "provider_account_id": account_id,
                            "provider_code": account.provider_code,
                            "subscription_id": internal_id,
                        },
                        instante=instante,
                    )
                )
                return binding_id
        except IntegrityError as exc:
            raise RegistroComercialDuplicado(
                "billing_subscription_binding_duplicate"
            ) from exc

    def receber_webhook(
        self,
        *,
        contexto: ContextoExecucao,
        provider_account_id: str,
        payload: bytes,
        headers: Mapping[str, str],
    ) -> FMBillingWebhookInboxORM:
        account_id = provider_account_id.strip()
        if not account_id or not payload:
            raise DadoComercialInvalido("billing_webhook_payload_invalido")
        digest = _body_hash(payload)
        call_context = BillingCallContext(
            idempotency_key=f"webhook-verify:{account_id}:{digest}",
            correlation_id=contexto.correlation_id,
            timeout_seconds=10.0,
        )

        with self._session_factory() as session:
            account, gateway = self._gateway_in_session(
                session=session,
                provider_account_id=account_id,
                require_webhooks=True,
            )
            verification = gateway.verify_webhook(
                payload=payload,
                headers={str(k).casefold(): str(v) for k, v in headers.items()},
                context=call_context,
            )
            event_id = (
                verification.event_id.strip()
                if verification.event_id and verification.event_id.strip()
                else f"invalid:{digest}"
            )
            provider_event_type = (
                verification.event_type.strip()[:128]
                if verification.event_type
                else None
            )

            if not verification.valid:
                return self._persist_rejected(
                    contexto=contexto,
                    provider_account_id=account_id,
                    provider_code=account.provider_code,
                    external_event_id=event_id,
                    provider_event_type=provider_event_type,
                    body_hash=digest,
                    reason="billing_webhook_signature_invalid",
                )

            normalized = gateway.normalize_webhook(
                payload=payload,
                verification=verification,
                context=BillingCallContext(
                    idempotency_key=f"webhook-normalize:{account_id}:{event_id}",
                    correlation_id=contexto.correlation_id,
                    timeout_seconds=10.0,
                ),
            )

        if normalized.provider_code != account.provider_code:
            raise DadoComercialInvalido("billing_webhook_provider_mismatch")
        if normalized.external_event_id != event_id:
            raise DadoComercialInvalido("billing_webhook_event_id_mismatch")

        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            existing = repo.obter_inbox_por_evento(
                provider_account_id=account_id,
                external_event_id=event_id,
            )
            if existing is not None:
                if existing.body_hash != digest:
                    raise ConflitoIdempotenciaComercial(
                        "billing_webhook_replay_body_conflict"
                    )
                return existing

            subscription_id: str | None = None
            if normalized.external_subscription_ref:
                binding = repo.obter_binding_por_external(
                    provider_account_id=account_id,
                    external_subscription_ref=normalized.external_subscription_ref,
                )
                if binding is not None:
                    if binding.provider_code != normalized.provider_code:
                        raise DadoComercialInvalido(
                            "billing_webhook_binding_provider_mismatch"
                        )
                    subscription_id = binding.subscription_id

            instante = _now()
            inbox = repo.adicionar_inbox(
                FMBillingWebhookInboxORM(
                    inbox_id=str(uuid4()),
                    provider_account_id=account_id,
                    provider_code=normalized.provider_code,
                    external_event_id=event_id,
                    provider_event_type=provider_event_type,
                    canonical_event_type=normalized.canonical_event_type.value,
                    body_hash=digest,
                    signature_valid=True,
                    status=BillingWebhookInboxStatus.VERIFIED.value,
                    received_at=instante,
                    provider_occurred_at=normalized.occurred_at,
                    provider_sequence=normalized.provider_sequence,
                    external_subscription_ref=normalized.external_subscription_ref,
                    external_transaction_ref=normalized.external_transaction_ref,
                    subscription_id=subscription_id,
                    normalized_payload=_event_payload(normalized),
                    attempts=0,
                    max_attempts=self._max_attempts,
                    last_error_code=None,
                    next_retry_at=None,
                    processed_at=None,
                    correlation_id=contexto.correlation_id,
                    causation_id=contexto.causation_id,
                    version=1,
                )
            )
            RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.webhook.received",
                    aggregate_type="billing_webhook",
                    aggregate_id=inbox.inbox_id,
                    result="success",
                    reason="KCA-10 durable webhook inbox",
                    metadata_safe={
                        "provider_account_id": account_id,
                        "provider_code": normalized.provider_code,
                        "external_event_id": event_id,
                        "canonical_event_type": normalized.canonical_event_type.value,
                        "body_hash": digest,
                    },
                    instante=instante,
                )
            )

        return self.processar_inbox(
            contexto=contexto,
            inbox_id=inbox.inbox_id,
        )

    def _persist_rejected(
        self,
        *,
        contexto: ContextoExecucao,
        provider_account_id: str,
        provider_code: str,
        external_event_id: str,
        provider_event_type: str | None,
        body_hash: str,
        reason: str,
    ) -> FMBillingWebhookInboxORM:
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            existing = repo.obter_inbox_por_evento(
                provider_account_id=provider_account_id,
                external_event_id=external_event_id,
            )
            if existing is not None:
                if existing.body_hash != body_hash:
                    raise ConflitoIdempotenciaComercial(
                        "billing_webhook_replay_body_conflict"
                    )
                return existing
            instante = _now()
            row = repo.adicionar_inbox(
                FMBillingWebhookInboxORM(
                    inbox_id=str(uuid4()),
                    provider_account_id=provider_account_id,
                    provider_code=provider_code,
                    external_event_id=external_event_id,
                    provider_event_type=provider_event_type,
                    canonical_event_type=None,
                    body_hash=body_hash,
                    signature_valid=False,
                    status=BillingWebhookInboxStatus.REJECTED.value,
                    received_at=instante,
                    provider_occurred_at=None,
                    provider_sequence=None,
                    external_subscription_ref=None,
                    external_transaction_ref=None,
                    subscription_id=None,
                    normalized_payload=None,
                    attempts=0,
                    max_attempts=self._max_attempts,
                    last_error_code=reason,
                    next_retry_at=None,
                    processed_at=instante,
                    correlation_id=contexto.correlation_id,
                    causation_id=contexto.causation_id,
                    version=1,
                )
            )
            RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.webhook.rejected",
                    aggregate_type="billing_webhook",
                    aggregate_id=row.inbox_id,
                    result="rejected",
                    reason=reason,
                    metadata_safe={
                        "provider_account_id": provider_account_id,
                        "provider_code": provider_code,
                        "external_event_id": external_event_id,
                        "body_hash": body_hash,
                    },
                    instante=instante,
                )
            )
            return row

    def _resolve_subscription_id(
        self,
        *,
        session,
        inbox: FMBillingWebhookInboxORM,
        event: NormalizedBillingEvent,
    ) -> str | None:
        if inbox.subscription_id:
            return inbox.subscription_id
        if not event.external_subscription_ref:
            return None
        binding = RepositorioBillingEventsSQLAlchemy(
            session
        ).obter_binding_por_external(
            provider_account_id=inbox.provider_account_id,
            external_subscription_ref=event.external_subscription_ref,
        )
        if binding is None:
            raise BillingBindingPending("billing_subscription_binding_pending")
        if binding.provider_code != inbox.provider_code:
            raise DadoComercialInvalido(
                "billing_subscription_binding_provider_mismatch"
            )
        return binding.subscription_id

    @staticmethod
    def _stream_key(
        *,
        event: NormalizedBillingEvent,
        subscription_id: str | None,
    ) -> str:
        if event.canonical_event_type in {
            BillingCanonicalEventType.PAYMENT_SUCCEEDED,
            BillingCanonicalEventType.PAYMENT_FAILED,
            BillingCanonicalEventType.PAYMENT_REFUNDED,
        }:
            if not event.external_transaction_ref:
                raise DadoComercialInvalido(
                    "billing_transaction_stream_ref_missing"
                )
            return f"transaction:{event.external_transaction_ref}"
        if not subscription_id:
            raise BillingBindingPending("billing_subscription_binding_pending")
        return f"subscription:{subscription_id}"

    def _mark_processing(
        self,
        *,
        inbox_id: str,
    ) -> FMBillingWebhookInboxORM:
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            inbox = repo.obter_inbox(inbox_id)
            if inbox is None:
                raise RegistroComercialNaoEncontrado("billing_webhook_not_found")
            if inbox.status in {
                BillingWebhookInboxStatus.PROCESSED.value,
                BillingWebhookInboxStatus.IGNORED_OUT_OF_ORDER.value,
                BillingWebhookInboxStatus.REJECTED.value,
            }:
                return inbox
            if inbox.status == BillingWebhookInboxStatus.DEAD_LETTER.value:
                raise DadoComercialInvalido("billing_webhook_dead_letter_requires_replay")
            return repo.atualizar_inbox(
                inbox_id=inbox.inbox_id,
                expected_version=inbox.version,
                values={
                    "status": BillingWebhookInboxStatus.PROCESSING.value,
                    "attempts": inbox.attempts + 1,
                    "next_retry_at": None,
                    "last_error_code": None,
                },
            )

    def processar_inbox(
        self,
        *,
        contexto: ContextoExecucao,
        inbox_id: str,
    ) -> FMBillingWebhookInboxORM:
        inbox = self._mark_processing(inbox_id=inbox_id)
        if inbox.status in {
            BillingWebhookInboxStatus.PROCESSED.value,
            BillingWebhookInboxStatus.IGNORED_OUT_OF_ORDER.value,
            BillingWebhookInboxStatus.REJECTED.value,
        }:
            return inbox
        if not inbox.normalized_payload:
            return self._falhar_inbox(
                contexto=contexto,
                inbox=inbox,
                error_code="billing_normalized_payload_missing",
                retryable=False,
            )

        try:
            event = _event_from_payload(dict(inbox.normalized_payload))
            with self._session_factory() as session:
                subscription_id = self._resolve_subscription_id(
                    session=session,
                    inbox=inbox,
                    event=event,
                )
                stream_key = self._stream_key(
                    event=event,
                    subscription_id=subscription_id,
                )
                cursor = RepositorioBillingEventsSQLAlchemy(session).obter_cursor(
                    provider_account_id=inbox.provider_account_id,
                    stream_key=stream_key,
                )
                if cursor is not None and is_out_of_order(
                    incoming_sequence=event.provider_sequence,
                    incoming_occurred_at=event.occurred_at,
                    last_sequence=cursor.last_provider_sequence,
                    last_occurred_at=cursor.last_occurred_at,
                ):
                    return self._mark_out_of_order(
                        contexto=contexto,
                        inbox=inbox,
                        subscription_id=subscription_id,
                        stream_key=stream_key,
                    )

            if event.canonical_event_type in {
                BillingCanonicalEventType.PAYMENT_SUCCEEDED,
                BillingCanonicalEventType.PAYMENT_FAILED,
                BillingCanonicalEventType.PAYMENT_REFUNDED,
            }:
                self._apply_transaction_event(
                    contexto=contexto,
                    inbox=inbox,
                    event=event,
                    subscription_id=subscription_id,
                )
            else:
                if not subscription_id:
                    raise BillingBindingPending(
                        "billing_subscription_binding_pending"
                    )
                self._apply_subscription_event(
                    contexto=contexto,
                    subscription_id=subscription_id,
                    event=event,
                )

            return self._finalize_processed(
                contexto=contexto,
                inbox=inbox,
                event=event,
                subscription_id=subscription_id,
                stream_key=stream_key,
            )
        except BillingBindingPending as exc:
            return self._falhar_inbox(
                contexto=contexto,
                inbox=inbox,
                error_code=str(exc),
                retryable=True,
            )
        except (ConflitoConcorrenciaComercial, BillingRetryableProcessingError) as exc:
            return self._falhar_inbox(
                contexto=contexto,
                inbox=inbox,
                error_code=type(exc).__name__,
                retryable=True,
            )
        except (
            DadoComercialInvalido,
            RegistroComercialNaoEncontrado,
            RegistroComercialDuplicado,
            TransicaoComercialInvalida,
            ValueError,
        ) as exc:
            return self._falhar_inbox(
                contexto=contexto,
                inbox=inbox,
                error_code=type(exc).__name__,
                retryable=False,
            )

    def _apply_transaction_event(
        self,
        *,
        contexto: ContextoExecucao,
        inbox: FMBillingWebhookInboxORM,
        event: NormalizedBillingEvent,
        subscription_id: str | None,
    ) -> None:
        if not event.external_transaction_ref:
            raise DadoComercialInvalido(
                "billing_external_transaction_ref_obrigatoria"
            )
        status = event.transaction_status or transaction_status_for_event(
            event.canonical_event_type
        )
        if status is None:
            raise DadoComercialInvalido("billing_transaction_status_missing")
        transaction_type = event.transaction_type or (
            BillingTransactionType.REFUND
            if event.canonical_event_type
            == BillingCanonicalEventType.PAYMENT_REFUNDED
            else BillingTransactionType.PAYMENT
        )
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            current = repo.obter_transacao_por_external(
                provider_account_id=inbox.provider_account_id,
                external_transaction_ref=event.external_transaction_ref,
            )
            values = {
                "subscription_id": subscription_id,
                "transaction_type": transaction_type.value,
                "status": status.value,
                "amount": event.amount,
                "currency": event.currency,
                "provider_occurred_at": event.occurred_at,
                "provider_sequence": event.provider_sequence,
                "last_external_event_id": event.external_event_id,
                "reconciliation_status": BillingReconciliationStatus.NOT_CHECKED.value,
                "last_reconciled_at": None,
                "correlation_id": contexto.correlation_id,
            }
            if current is None:
                repo.adicionar_transacao(
                    FMBillingTransactionORM(
                        billing_transaction_id=str(uuid4()),
                        provider_account_id=inbox.provider_account_id,
                        provider_code=inbox.provider_code,
                        external_transaction_ref=event.external_transaction_ref,
                        subscription_id=subscription_id,
                        transaction_type=transaction_type.value,
                        status=status.value,
                        amount=event.amount,
                        currency=event.currency,
                        provider_occurred_at=event.occurred_at,
                        provider_sequence=event.provider_sequence,
                        last_external_event_id=event.external_event_id,
                        reconciliation_status=(
                            BillingReconciliationStatus.NOT_CHECKED.value
                        ),
                        last_reconciled_at=None,
                        version=1,
                        correlation_id=contexto.correlation_id,
                        created_at=_now(),
                        updated_at=_now(),
                    )
                )
            else:
                if current.provider_code != inbox.provider_code:
                    raise DadoComercialInvalido(
                        "billing_transaction_provider_mismatch"
                    )
                repo.atualizar_transacao(
                    billing_transaction_id=current.billing_transaction_id,
                    expected_version=current.version,
                    values=values,
                )

    def _apply_subscription_event(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        event: NormalizedBillingEvent,
    ) -> None:
        with self._session_factory() as session:
            current = RepositorioSubscriptionComercialSQLAlchemy(
                session
            ).obter(subscription_id)
        if current is None:
            raise RegistroComercialNaoEncontrado("subscription_not_found")

        event_type = event.canonical_event_type
        if event_type == BillingCanonicalEventType.SUBSCRIPTION_ACTIVE:
            if current.status == EstadoAssinatura.ACTIVE:
                return
            if current.status == EstadoAssinatura.PENDING:
                if event.period_start is None or event.period_end is None:
                    raise DadoComercialInvalido(
                        "billing_subscription_active_period_required"
                    )
                self._subscription.ativar(
                    contexto=contexto,
                    subscription_id=subscription_id,
                    expected_version=current.version,
                    current_period_start=event.period_start,
                    current_period_end=event.period_end,
                )
                return
            self._subscription.reativar(
                contexto=contexto,
                subscription_id=subscription_id,
                expected_version=current.version,
            )
            return
        if event_type == BillingCanonicalEventType.SUBSCRIPTION_PAST_DUE:
            self._subscription.marcar_past_due(
                contexto=contexto,
                subscription_id=subscription_id,
                expected_version=current.version,
            )
            return
        if event_type == BillingCanonicalEventType.SUBSCRIPTION_SUSPENDED:
            self._subscription.suspender(
                contexto=contexto,
                subscription_id=subscription_id,
                expected_version=current.version,
                motivo="KCA-10 provider normalized event",
            )
            return
        if event_type == BillingCanonicalEventType.SUBSCRIPTION_CANCELED:
            self._subscription.cancelar(
                contexto=contexto,
                subscription_id=subscription_id,
                expected_version=current.version,
                motivo="KCA-10 provider normalized event",
            )
            return
        if event_type == BillingCanonicalEventType.SUBSCRIPTION_RENEWED:
            if event.period_start is None or event.period_end is None:
                raise DadoComercialInvalido(
                    "billing_subscription_renewal_period_required"
                )
            self._subscription.renovar(
                contexto=contexto,
                subscription_id=subscription_id,
                expected_version=current.version,
                current_period_start=event.period_start,
                current_period_end=event.period_end,
            )
            return
        raise DadoComercialInvalido("billing_subscription_event_unsupported")

    def _mark_out_of_order(
        self,
        *,
        contexto: ContextoExecucao,
        inbox: FMBillingWebhookInboxORM,
        subscription_id: str | None,
        stream_key: str,
    ) -> FMBillingWebhookInboxORM:
        instante = _now()
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            current = repo.obter_inbox(inbox.inbox_id)
            if current is None:
                raise RegistroComercialNaoEncontrado("billing_webhook_not_found")
            updated = repo.atualizar_inbox(
                inbox_id=current.inbox_id,
                expected_version=current.version,
                values={
                    "status": BillingWebhookInboxStatus.IGNORED_OUT_OF_ORDER.value,
                    "subscription_id": subscription_id,
                    "processed_at": instante,
                    "last_error_code": "billing_event_out_of_order",
                },
            )
            RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.webhook.out_of_order",
                    aggregate_type="billing_webhook",
                    aggregate_id=inbox.inbox_id,
                    result="ignored",
                    reason="KCA-10 ordering protection",
                    metadata_safe={
                        "stream_key": stream_key,
                        "external_event_id": inbox.external_event_id,
                    },
                    instante=instante,
                )
            )
            return updated

    def _finalize_processed(
        self,
        *,
        contexto: ContextoExecucao,
        inbox: FMBillingWebhookInboxORM,
        event: NormalizedBillingEvent,
        subscription_id: str | None,
        stream_key: str,
    ) -> FMBillingWebhookInboxORM:
        instante = _now()
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            current = repo.obter_inbox(inbox.inbox_id)
            if current is None:
                raise RegistroComercialNaoEncontrado("billing_webhook_not_found")
            cursor = repo.obter_cursor(
                provider_account_id=inbox.provider_account_id,
                stream_key=stream_key,
            )
            if cursor is None:
                repo.adicionar_cursor(
                    FMBillingEventCursorORM(
                        cursor_id=str(uuid4()),
                        provider_account_id=inbox.provider_account_id,
                        provider_code=inbox.provider_code,
                        stream_key=stream_key,
                        last_provider_sequence=event.provider_sequence,
                        last_occurred_at=event.occurred_at,
                        last_external_event_id=event.external_event_id,
                        version=1,
                        updated_at=instante,
                    )
                )
            else:
                if is_out_of_order(
                    incoming_sequence=event.provider_sequence,
                    incoming_occurred_at=event.occurred_at,
                    last_sequence=cursor.last_provider_sequence,
                    last_occurred_at=cursor.last_occurred_at,
                ):
                    ignored = repo.atualizar_inbox(
                        inbox_id=current.inbox_id,
                        expected_version=current.version,
                        values={
                            "status": BillingWebhookInboxStatus.IGNORED_OUT_OF_ORDER.value,
                            "subscription_id": subscription_id,
                            "processed_at": instante,
                            "last_error_code": "billing_event_out_of_order",
                        },
                    )
                    RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                        self._audit(
                            contexto=contexto,
                            action="commercial.billing.webhook.out_of_order",
                            aggregate_type="billing_webhook",
                            aggregate_id=current.inbox_id,
                            result="ignored",
                            reason="KCA-10 ordering protection",
                            metadata_safe={
                                "stream_key": stream_key,
                                "external_event_id": event.external_event_id,
                            },
                            instante=instante,
                        )
                    )
                    return ignored
                repo.atualizar_cursor(
                    cursor_id=cursor.cursor_id,
                    expected_version=cursor.version,
                    values={
                        "last_provider_sequence": event.provider_sequence,
                        "last_occurred_at": event.occurred_at,
                        "last_external_event_id": event.external_event_id,
                    },
                )
            updated = repo.atualizar_inbox(
                inbox_id=current.inbox_id,
                expected_version=current.version,
                values={
                    "status": BillingWebhookInboxStatus.PROCESSED.value,
                    "subscription_id": subscription_id,
                    "processed_at": instante,
                    "last_error_code": None,
                    "next_retry_at": None,
                },
            )
            RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.webhook.processed",
                    aggregate_type="billing_webhook",
                    aggregate_id=inbox.inbox_id,
                    result="success",
                    reason="KCA-10 normalized billing event applied",
                    metadata_safe={
                        "stream_key": stream_key,
                        "external_event_id": event.external_event_id,
                        "canonical_event_type": event.canonical_event_type.value,
                        "attempts": updated.attempts,
                    },
                    instante=instante,
                )
            )
            return updated

    def _falhar_inbox(
        self,
        *,
        contexto: ContextoExecucao,
        inbox: FMBillingWebhookInboxORM,
        error_code: str,
        retryable: bool,
    ) -> FMBillingWebhookInboxORM:
        instante = _now()
        code = _safe_code(error_code, fallback="billing_processing_error")
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            current = repo.obter_inbox(inbox.inbox_id)
            if current is None:
                raise RegistroComercialNaoEncontrado("billing_webhook_not_found")
            exhausted = current.attempts >= current.max_attempts
            status = (
                BillingWebhookInboxStatus.FAILED_RETRYABLE
                if retryable and not exhausted
                else BillingWebhookInboxStatus.DEAD_LETTER
            )
            next_retry = None
            if status == BillingWebhookInboxStatus.FAILED_RETRYABLE:
                delay = min(
                    3600,
                    self._retry_base_seconds * (2 ** max(0, current.attempts - 1)),
                )
                next_retry = instante + timedelta(seconds=delay)
            updated = repo.atualizar_inbox(
                inbox_id=current.inbox_id,
                expected_version=current.version,
                values={
                    "status": status.value,
                    "last_error_code": code,
                    "next_retry_at": next_retry,
                    "processed_at": (
                        instante
                        if status == BillingWebhookInboxStatus.DEAD_LETTER
                        else None
                    ),
                },
            )
            RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.webhook.failed",
                    aggregate_type="billing_webhook",
                    aggregate_id=current.inbox_id,
                    result=(
                        "retryable"
                        if status
                        == BillingWebhookInboxStatus.FAILED_RETRYABLE
                        else "dead_letter"
                    ),
                    reason=code,
                    metadata_safe={
                        "attempts": updated.attempts,
                        "max_attempts": updated.max_attempts,
                        "status": updated.status,
                    },
                    instante=instante,
                )
            )
            return updated

    def obter_inbox(self, *, inbox_id: str) -> FMBillingWebhookInboxORM:
        with self._session_factory() as session:
            row = RepositorioBillingEventsSQLAlchemy(session).obter_inbox(
                inbox_id.strip()
            )
        if row is None:
            raise RegistroComercialNaoEncontrado("billing_webhook_not_found")
        return row

    def listar_inbox(
        self,
        *,
        status: BillingWebhookInboxStatus,
        limit: int = 100,
    ) -> tuple[FMBillingWebhookInboxORM, ...]:
        if limit < 1 or limit > 500:
            raise DadoComercialInvalido("billing_inbox_limit_invalido")
        with self._session_factory() as session:
            return RepositorioBillingEventsSQLAlchemy(
                session
            ).listar_inbox_por_status(status=status.value, limit=limit)

    def obter_transacao(
        self, *, billing_transaction_id: str
    ) -> FMBillingTransactionORM:
        with self._session_factory() as session:
            row = RepositorioBillingEventsSQLAlchemy(session).obter_transacao(
                billing_transaction_id.strip()
            )
        if row is None:
            raise RegistroComercialNaoEncontrado("billing_transaction_not_found")
        return row

    def processar_retries(
        self,
        *,
        contexto: ContextoExecucao,
        now: datetime | None = None,
        limit: int = 100,
    ) -> tuple[str, ...]:
        instante = now or _now()
        with self._session_factory() as session:
            due = RepositorioBillingEventsSQLAlchemy(session).listar_retryable_due(
                now=instante,
                limit=limit,
            )
            ids = tuple(row.inbox_id for row in due)
        for inbox_id in ids:
            self.processar_inbox(contexto=contexto, inbox_id=inbox_id)
        return ids

    def reprocessar_dead_letter(
        self,
        *,
        contexto: ContextoExecucao,
        inbox_id: str,
        expected_version: int,
    ) -> FMBillingWebhookInboxORM:
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            current = repo.obter_inbox(inbox_id.strip())
            if current is None:
                raise RegistroComercialNaoEncontrado("billing_webhook_not_found")
            if current.status != BillingWebhookInboxStatus.DEAD_LETTER.value:
                raise DadoComercialInvalido(
                    "billing_webhook_replay_requires_dead_letter"
                )
            reset = repo.atualizar_inbox(
                inbox_id=current.inbox_id,
                expected_version=expected_version,
                values={
                    "status": BillingWebhookInboxStatus.VERIFIED.value,
                    "attempts": 0,
                    "last_error_code": None,
                    "next_retry_at": None,
                    "processed_at": None,
                    "correlation_id": contexto.correlation_id,
                    "causation_id": current.inbox_id,
                },
            )
            RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.webhook.replay",
                    aggregate_type="billing_webhook",
                    aggregate_id=current.inbox_id,
                    result="authorized",
                    reason="KCA-10 controlled dead-letter replay",
                    metadata_safe={
                        "external_event_id": current.external_event_id,
                        "body_hash": current.body_hash,
                    },
                    instante=_now(),
                )
            )
        return self.processar_inbox(
            contexto=contexto,
            inbox_id=reset.inbox_id,
        )

    def reconciliar_transacao(
        self,
        *,
        contexto: ContextoExecucao,
        billing_transaction_id: str,
    ) -> FMBillingTransactionORM:
        transaction_id = billing_transaction_id.strip()
        instante = _now()
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            transaction = repo.obter_transacao(transaction_id)
            if transaction is None:
                raise RegistroComercialNaoEncontrado(
                    "billing_transaction_not_found"
                )
            run_id = str(uuid4())
            repo.adicionar_reconciliation_run(
                FMBillingReconciliationRunORM(
                    reconciliation_run_id=run_id,
                    provider_account_id=transaction.provider_account_id,
                    billing_transaction_id=transaction.billing_transaction_id,
                    status="started",
                    previous_status=transaction.status,
                    provider_status=None,
                    final_status=None,
                    error_code=None,
                    correlation_id=contexto.correlation_id,
                    started_at=instante,
                    completed_at=None,
                )
            )
            provider_account_id = transaction.provider_account_id
            external_ref = transaction.external_transaction_ref

        try:
            with self._session_factory() as session:
                _, gateway = self._gateway_in_session(
                    session=session,
                    provider_account_id=provider_account_id,
                    require_webhooks=False,
                )
                provider_tx = gateway.fetch_transaction(
                    external_transaction_ref=external_ref,
                    context=BillingCallContext(
                        idempotency_key=f"reconcile:{transaction_id}:{run_id}",
                        correlation_id=contexto.correlation_id,
                        timeout_seconds=15.0,
                    ),
                )
            return self._aplicar_reconciliation(
                contexto=contexto,
                run_id=run_id,
                transaction_id=transaction_id,
                provider_tx=provider_tx,
            )
        except (
            BillingProviderError,
            DadoComercialInvalido,
            ReferenciaSegredoInvalida,
            SegredoAusente,
            RuntimeError,
        ) as exc:
            code = _safe_code(type(exc).__name__, fallback="billing_reconciliation_error")
            with self._session_factory() as session, session.begin():
                repo = RepositorioBillingEventsSQLAlchemy(session)
                current = repo.obter_transacao(transaction_id)
                if current is not None:
                    repo.atualizar_transacao(
                        billing_transaction_id=current.billing_transaction_id,
                        expected_version=current.version,
                        values={
                            "reconciliation_status": BillingReconciliationStatus.FAILED.value,
                            "last_reconciled_at": _now(),
                            "correlation_id": contexto.correlation_id,
                        },
                    )
                repo.atualizar_reconciliation_run(
                    reconciliation_run_id=run_id,
                    values={
                        "status": "failed",
                        "error_code": code,
                        "completed_at": _now(),
                    },
                )
            raise

    def _aplicar_reconciliation(
        self,
        *,
        contexto: ContextoExecucao,
        run_id: str,
        transaction_id: str,
        provider_tx: BillingTransaction,
    ) -> FMBillingTransactionORM:
        provider_status = _canonical_provider_transaction_status(provider_tx.status)
        instante = _now()
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingEventsSQLAlchemy(session)
            current = repo.obter_transacao(transaction_id)
            if current is None:
                raise RegistroComercialNaoEncontrado(
                    "billing_transaction_not_found"
                )
            if provider_tx.provider_code.strip().upper() != current.provider_code:
                raise DadoComercialInvalido(
                    "billing_reconciliation_provider_mismatch"
                )
            if provider_tx.external_transaction_ref != current.external_transaction_ref:
                raise DadoComercialInvalido(
                    "billing_reconciliation_transaction_ref_mismatch"
                )
            amount_changed = (
                provider_tx.amount is not None
                and (
                    current.amount is None
                    or Decimal(provider_tx.amount) != Decimal(current.amount)
                )
            )
            currency_changed = (
                provider_tx.currency
                and (
                    current.currency is None
                    or provider_tx.currency.upper() != current.currency.upper()
                )
            )
            status_changed = provider_status.value != current.status
            repaired = status_changed or amount_changed or currency_changed
            values: dict[str, object] = {
                "reconciliation_status": (
                    BillingReconciliationStatus.REPAIRED.value
                    if repaired
                    else BillingReconciliationStatus.IN_SYNC.value
                ),
                "last_reconciled_at": instante,
                "correlation_id": contexto.correlation_id,
            }
            if repaired:
                values.update(
                    {
                        "status": provider_status.value,
                        "amount": provider_tx.amount,
                        "currency": provider_tx.currency.upper(),
                    }
                )
            updated = repo.atualizar_transacao(
                billing_transaction_id=current.billing_transaction_id,
                expected_version=current.version,
                values=values,
            )
            repo.atualizar_reconciliation_run(
                reconciliation_run_id=run_id,
                values={
                    "status": "repaired" if repaired else "in_sync",
                    "provider_status": provider_status.value,
                    "final_status": updated.status,
                    "completed_at": instante,
                },
            )
            RepositorioComercialSQLAlchemy(session).adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.reconciliation",
                    aggregate_type="billing_transaction",
                    aggregate_id=updated.billing_transaction_id,
                    result="repaired" if repaired else "in_sync",
                    reason="KCA-10 provider reconciliation",
                    metadata_safe={
                        "previous_status": current.status,
                        "provider_status": provider_status.value,
                        "final_status": updated.status,
                        "amount_changed": amount_changed,
                        "currency_changed": currency_changed,
                    },
                    instante=instante,
                )
            )
            return updated
