"""Application boundary do Subscription Engine KCA-08."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from application.commercial_trial import AplicacaoTrialComercialV1
from core.comercial.catalogo import StatusConfiguracaoCatalogo, normalizar_plan_code
from core.comercial.entitlement import (
    EstadoComercial,
    SnapshotEntitlement,
    serializar_capabilities,
)
from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
)
from core.comercial.modelos import StatusClienteComercial, StatusContaProduto
from core.comercial.subscription import (
    AssinaturaComercial,
    EstadoAssinatura,
    utc,
    validar_periodo,
    validar_transicao_assinatura,
)
from core.comercial.trial import EstadoTrial
from core.seguranca.contexto import ContextoExecucao
from infra.comercial.catalogo_sqlalchemy import RepositorioCatalogoComercialSQLAlchemy
from infra.comercial.modelos_orm import CommercialAuditORM, CommercialOutboxORM
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy
from infra.comercial.subscription_orm import FMCommercialSubscriptionORM
from infra.comercial.subscription_sqlalchemy import (
    RepositorioSubscriptionComercialSQLAlchemy,
)
from infra.comercial.trial_sqlalchemy import RepositorioTrialComercialSQLAlchemy


@dataclass(frozen=True, kw_only=True)
class ResultadoAtivacaoAssinatura:
    subscription: AssinaturaComercial
    entitlement_snapshot_id: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(value: str) -> str:
    result = value.strip()
    if not result or len(result) > 192:
        raise DadoComercialInvalido("idempotency_key_invalida")
    return result


def _hash_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AplicacaoSubscriptionComercialV1:
    def __init__(
        self,
        session_factory,
        *,
        restricted_entitlement_lease_seconds: int = 3600,
    ) -> None:
        if restricted_entitlement_lease_seconds < 60:
            raise ValueError("restricted_entitlement_lease_seconds_invalido")
        self._session_factory = session_factory
        self._restricted_lease = timedelta(
            seconds=restricted_entitlement_lease_seconds
        )
        self._entitlement = AplicacaoEntitlementComercialV1(session_factory)
        self._trial = AplicacaoTrialComercialV1(session_factory)

    @staticmethod
    def _actor(contexto: ContextoExecucao) -> str:
        return contexto.identity_user_id or contexto.usuario_id

    @staticmethod
    def _validate_scope(contexto: ContextoExecucao, *, tenant_id: str) -> None:
        if not contexto.identidade_sistema and contexto.tenant_id != tenant_id:
            raise PermissionError("seguranca.tenant_nao_autorizado")

    @staticmethod
    def _audit(
        *,
        contexto: ContextoExecucao,
        action: str,
        subscription: AssinaturaComercial,
        reason: str,
        instante: datetime,
        metadata: dict[str, object] | None = None,
    ) -> CommercialAuditORM:
        safe = {
            "fm_customer_id": subscription.fm_customer_id,
            "product_account_id": subscription.product_account_id,
            "tenant_id": subscription.tenant_id,
            "plan_code": subscription.plan_code,
            "plan_version_id": subscription.plan_version_id,
            "price_id": subscription.price_id,
            "status": subscription.status.value,
            "version": subscription.version,
        }
        safe.update(metadata or {})
        return CommercialAuditORM(
            audit_id=str(uuid4()),
            actor_user_id=AplicacaoSubscriptionComercialV1._actor(contexto),
            action=action,
            aggregate_type="subscription",
            aggregate_id=subscription.subscription_id,
            result="success",
            reason=reason[:255],
            correlation_id=contexto.correlation_id,
            causation_id=contexto.causation_id,
            metadata_safe=safe,
            timestamp=instante,
        )

    @staticmethod
    def _event(
        *,
        contexto: ContextoExecucao,
        event_type: str,
        subscription: AssinaturaComercial,
        instante: datetime,
    ) -> CommercialOutboxORM:
        return CommercialOutboxORM(
            event_id=str(uuid4()),
            event_type=event_type,
            aggregate_type="subscription",
            aggregate_id=subscription.subscription_id,
            fm_customer_id=subscription.fm_customer_id,
            product_account_id=subscription.product_account_id,
            product_code="KORDENA",
            product_tenant_id=subscription.tenant_id,
            correlation_id=contexto.correlation_id,
            causation_id=contexto.causation_id,
            idempotency_key=(
                f"subscription:{subscription.subscription_id}:"
                f"{event_type}:v{subscription.version}"
            ),
            occurred_at=instante,
            payload={
                "subscription_id": subscription.subscription_id,
                "fm_customer_id": subscription.fm_customer_id,
                "product_account_id": subscription.product_account_id,
                "tenant_id": subscription.tenant_id,
                "plan_code": subscription.plan_code,
                "plan_version_id": subscription.plan_version_id,
                "price_id": subscription.price_id,
                "currency": subscription.currency,
                "billing_period": subscription.billing_period,
                "contracted_amount": str(subscription.contracted_amount),
                "status": subscription.status.value,
                "current_period_start": (
                    subscription.current_period_start.isoformat()
                    if subscription.current_period_start
                    else None
                ),
                "current_period_end": (
                    subscription.current_period_end.isoformat()
                    if subscription.current_period_end
                    else None
                ),
                "cancel_at_period_end": subscription.cancel_at_period_end,
            },
            version=1,
            status="pending",
        )

    def _project(self, snapshot: SnapshotEntitlement) -> None:
        applied = self._entitlement.aplicar_evento_local(
            event_id=f"subscription-{snapshot.entitlement_snapshot_id}",
            payload={
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
            },
        )
        if applied:
            return
        decision = self._entitlement.avaliar_local(
            tenant_id=snapshot.tenant_id,
            product_account_id=snapshot.product_account_id,
        )
        if decision.revision is None or decision.revision < snapshot.revision:
            raise RuntimeError("subscription_entitlement_projection_not_applied")

    def _sync_entitlement(
        self,
        *,
        contexto: ContextoExecucao,
        subscription: AssinaturaComercial,
        reason: str,
    ) -> str:
        now = _now()
        state_by_status = {
            EstadoAssinatura.PENDING: EstadoComercial.CONFIGURATION_PENDING,
            EstadoAssinatura.ACTIVE: EstadoComercial.SUBSCRIPTION_ACTIVE,
            EstadoAssinatura.PAST_DUE: EstadoComercial.PAST_DUE,
            EstadoAssinatura.SUSPENDED: EstadoComercial.SUSPENDED,
            EstadoAssinatura.CANCELED: EstadoComercial.CANCELED,
        }
        state = state_by_status[subscription.status]
        if (
            subscription.status == EstadoAssinatura.ACTIVE
            and subscription.current_period_end is not None
            and utc(subscription.current_period_end) > now
        ):
            valid_until = utc(subscription.current_period_end)
        else:
            valid_until = now + self._restricted_lease
        snapshot = self._entitlement.recalcular(
            contexto=contexto,
            idempotency_key=(
                f"subscription:{subscription.subscription_id}:"
                f"entitlement:v{subscription.version}"
            ),
            product_account_id=subscription.product_account_id,
            tenant_id=subscription.tenant_id,
            commercial_state=state,
            plan_code=subscription.plan_code,
            valid_until=valid_until,
            change_reason=reason,
            plan_version_id=subscription.plan_version_id,
        )
        self._project(snapshot)
        return snapshot.entitlement_snapshot_id

    @staticmethod
    def _validate_catalog_binding(
        *,
        shared: RepositorioComercialSQLAlchemy,
        catalog: RepositorioCatalogoComercialSQLAlchemy,
        fm_customer_id: str,
        product_account_id: str,
        tenant_id: str,
        plan_code: str,
        plan_version_id: str,
        price_id: str,
        instante: datetime,
    ):
        customer = shared.obter_cliente(fm_customer_id)
        if customer is None:
            raise RegistroComercialNaoEncontrado("customer_not_found")
        if customer.status != StatusClienteComercial.ACTIVE:
            raise DadoComercialInvalido("customer_not_active")
        account = shared.obter_conta_produto(product_account_id)
        if account is None:
            raise RegistroComercialNaoEncontrado("product_account_not_found")
        if account.fm_customer_id != fm_customer_id:
            raise DadoComercialInvalido("subscription_customer_account_mismatch")
        if account.product_code != "KORDENA":
            raise DadoComercialInvalido("product_code_nao_suportado")
        if account.status != StatusContaProduto.ACTIVE:
            raise DadoComercialInvalido("product_account_not_active")
        if account.product_tenant_id != tenant_id:
            raise PermissionError("seguranca.tenant_product_account_mismatch")

        code = normalizar_plan_code(plan_code)
        plan = catalog.obter_plano_por_codigo(plan_code=code)
        if plan is None:
            raise RegistroComercialNaoEncontrado("plan_not_found")
        version = catalog.obter_versao_plano(
            plan_version_id=plan_version_id.strip()
        )
        if version is None:
            raise RegistroComercialNaoEncontrado("plan_version_not_found")
        if version.plan_id != plan.plan_id:
            raise DadoComercialInvalido("plan_version_nao_pertence_ao_plano")
        if version.status != StatusConfiguracaoCatalogo.PUBLISHED:
            raise DadoComercialInvalido("plan_version_not_published")
        if version.valid_from is None or version.valid_from > instante:
            raise DadoComercialInvalido("plan_version_not_effective")
        if version.valid_until is not None and version.valid_until <= instante:
            raise DadoComercialInvalido("plan_version_expired")

        price = catalog.obter_preco(price_id=price_id.strip())
        if price is None:
            raise RegistroComercialNaoEncontrado("price_not_found")
        if price.plan_version_id != version.plan_version_id:
            raise DadoComercialInvalido("price_plan_version_mismatch")
        if price.status != StatusConfiguracaoCatalogo.PUBLISHED:
            raise DadoComercialInvalido("price_not_published")
        if price.valid_from is None or price.valid_from > instante:
            raise DadoComercialInvalido("price_not_effective")
        if price.valid_until is not None and price.valid_until <= instante:
            raise DadoComercialInvalido("price_expired")
        return customer, account, plan, version, price

    def criar_pendente(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        fm_customer_id: str,
        product_account_id: str,
        tenant_id: str,
        plan_code: str,
        plan_version_id: str,
        price_id: str,
    ) -> AssinaturaComercial:
        key = _key(idempotency_key)
        customer_id = fm_customer_id.strip()
        account_id = product_account_id.strip()
        tenant = tenant_id.strip()
        if not customer_id or not account_id or not tenant:
            raise DadoComercialInvalido("subscription_campos_obrigatorios")
        self._validate_scope(contexto, tenant_id=tenant)
        code = normalizar_plan_code(plan_code)
        pv = plan_version_id.strip()
        price_ref = price_id.strip()
        if not pv or not price_ref:
            raise DadoComercialInvalido("subscription_catalog_binding_obrigatorio")

        request_sha256 = _hash_payload(
            {
                "fm_customer_id": customer_id,
                "product_account_id": account_id,
                "tenant_id": tenant,
                "plan_code": code,
                "plan_version_id": pv,
                "price_id": price_ref,
            }
        )
        scope = f"subscription.create:{account_id}"
        instante = _now()

        try:
            with self._session_factory() as session, session.begin():
                shared = RepositorioComercialSQLAlchemy(session)
                catalog = RepositorioCatalogoComercialSQLAlchemy(session)
                subscriptions = RepositorioSubscriptionComercialSQLAlchemy(session)
                existing_key = shared.obter_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                )
                if existing_key is not None:
                    if existing_key.request_sha256 != request_sha256:
                        raise ConflitoIdempotenciaComercial(
                            "subscription_idempotency_payload_conflict"
                        )
                    if existing_key.aggregate_type != "subscription":
                        raise ConflitoIdempotenciaComercial(
                            "subscription_idempotency_scope_conflict"
                        )
                    result = subscriptions.obter(existing_key.aggregate_id)
                    if result is None:
                        raise ConflitoIdempotenciaComercial(
                            "subscription_idempotency_result_missing"
                        )
                    return result

                _, _, _, _, price = self._validate_catalog_binding(
                    shared=shared,
                    catalog=catalog,
                    fm_customer_id=customer_id,
                    product_account_id=account_id,
                    tenant_id=tenant,
                    plan_code=code,
                    plan_version_id=pv,
                    price_id=price_ref,
                    instante=instante,
                )
                existing = subscriptions.obter_por_product_account(account_id)
                if existing is not None:
                    raise RegistroComercialDuplicado(
                        "subscription_product_account_duplicate"
                    )

                result = subscriptions.adicionar(
                    FMCommercialSubscriptionORM(
                        subscription_id=str(uuid4()),
                        fm_customer_id=customer_id,
                        product_account_id=account_id,
                        tenant_id=tenant,
                        plan_code=code,
                        plan_version_id=pv,
                        price_id=price.price_id,
                        currency=price.currency,
                        billing_period=price.billing_period,
                        contracted_amount=price.amount,
                        status=EstadoAssinatura.PENDING.value,
                        current_period_start=None,
                        current_period_end=None,
                        cancel_at_period_end=False,
                        canceled_at=None,
                        activated_at=None,
                        suspended_at=None,
                        version=1,
                        correlation_id=contexto.correlation_id,
                        created_at=instante,
                        updated_at=instante,
                    )
                )
                shared.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="subscription",
                    aggregate_id=result.subscription_id,
                    created_at=instante,
                )
                shared.adicionar_auditoria(
                    self._audit(
                        contexto=contexto,
                        action="commercial.subscription.create",
                        subscription=result,
                        reason="KCA-08 subscription pending",
                        instante=instante,
                    )
                )
                shared.adicionar_outbox(
                    self._event(
                        contexto=contexto,
                        event_type="subscription.created",
                        subscription=result,
                        instante=instante,
                    )
                )
                return result
        except IntegrityError as exc:
            raise RegistroComercialDuplicado("subscription_duplicate") from exc

    def obter_por_product_account(
        self,
        *,
        product_account_id: str,
    ) -> AssinaturaComercial | None:
        with self._session_factory() as session:
            return RepositorioSubscriptionComercialSQLAlchemy(
                session
            ).obter_por_product_account(product_account_id.strip())

    def ativar(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
        current_period_start: datetime,
        current_period_end: datetime,
    ) -> ResultadoAtivacaoAssinatura:
        start, end = validar_periodo(current_period_start, current_period_end)
        instante = _now()
        if end <= instante:
            raise DadoComercialInvalido("subscription_period_end_not_future")

        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioSubscriptionComercialSQLAlchemy(session)
            current = repo.obter(subscription_id.strip())
            if current is None:
                raise RegistroComercialNaoEncontrado("subscription_not_found")
            self._validate_scope(contexto, tenant_id=current.tenant_id)
            if current.status == EstadoAssinatura.ACTIVE:
                result = current
            else:
                if current.version != expected_version:
                    raise DadoComercialInvalido("subscription_expected_version_stale")
                validar_transicao_assinatura(
                    current.status,
                    EstadoAssinatura.ACTIVE,
                )
                trial = RepositorioTrialComercialSQLAlchemy(
                    session
                ).obter_por_product_account(current.product_account_id)
                if trial is not None:
                    if (
                        trial.fm_customer_id != current.fm_customer_id
                        or trial.tenant_id != current.tenant_id
                    ):
                        raise DadoComercialInvalido(
                            "subscription_trial_binding_mismatch"
                        )
                    if trial.status == EstadoTrial.ACTIVE:
                        self._trial.marcar_convertido_em_transacao(
                            session=session,
                            contexto=contexto,
                            trial_id=trial.trial_id,
                            instante=instante,
                        )
                    elif trial.status != EstadoTrial.CONVERTED:
                        raise DadoComercialInvalido(
                            f"subscription_trial_not_convertible:{trial.status.value}"
                        )
                values: dict[str, object] = {
                    "status": EstadoAssinatura.ACTIVE.value,
                    "current_period_start": start,
                    "current_period_end": end,
                    "cancel_at_period_end": False,
                    "suspended_at": None,
                }
                if current.activated_at is None:
                    values["activated_at"] = instante
                result = repo.atualizar(
                    subscription_id=current.subscription_id,
                    expected_version=current.version,
                    values=values,
                )
                shared.adicionar_auditoria(
                    self._audit(
                        contexto=contexto,
                        action="commercial.subscription.activated",
                        subscription=result,
                        reason="KCA-08 subscription activation",
                        instante=instante,
                    )
                )
                shared.adicionar_outbox(
                    self._event(
                        contexto=contexto,
                        event_type="subscription.activated",
                        subscription=result,
                        instante=instante,
                    )
                )

        snapshot_id = self._sync_entitlement(
            contexto=contexto,
            subscription=result,
            reason="KCA-08 subscription active",
        )
        return ResultadoAtivacaoAssinatura(
            subscription=result,
            entitlement_snapshot_id=snapshot_id,
        )

    def _transition(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
        destino: EstadoAssinatura,
        event_type: str,
        reason: str,
    ) -> AssinaturaComercial:
        instante = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioSubscriptionComercialSQLAlchemy(session)
            current = repo.obter(subscription_id.strip())
            if current is None:
                raise RegistroComercialNaoEncontrado("subscription_not_found")
            self._validate_scope(contexto, tenant_id=current.tenant_id)
            if current.status == destino:
                return current
            if current.version != expected_version:
                raise DadoComercialInvalido("subscription_expected_version_stale")
            validar_transicao_assinatura(current.status, destino)
            values: dict[str, object] = {"status": destino.value}
            if destino == EstadoAssinatura.SUSPENDED:
                values["suspended_at"] = instante
            elif destino == EstadoAssinatura.ACTIVE:
                values["suspended_at"] = None
            elif destino == EstadoAssinatura.CANCELED:
                values["canceled_at"] = instante
                values["cancel_at_period_end"] = False
            result = repo.atualizar(
                subscription_id=current.subscription_id,
                expected_version=current.version,
                values=values,
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action=f"commercial.subscription.{destino.value}",
                    subscription=result,
                    reason=reason,
                    instante=instante,
                )
            )
            shared.adicionar_outbox(
                self._event(
                    contexto=contexto,
                    event_type=event_type,
                    subscription=result,
                    instante=instante,
                )
            )
        self._sync_entitlement(
            contexto=contexto,
            subscription=result,
            reason=reason,
        )
        return result

    def marcar_past_due(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
    ) -> AssinaturaComercial:
        return self._transition(
            contexto=contexto,
            subscription_id=subscription_id,
            expected_version=expected_version,
            destino=EstadoAssinatura.PAST_DUE,
            event_type="subscription.past_due",
            reason="KCA-08 subscription past due",
        )

    def suspender(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
        motivo: str,
    ) -> AssinaturaComercial:
        reason = " ".join(motivo.split())
        if not reason:
            raise DadoComercialInvalido("subscription_suspend_reason_required")
        return self._transition(
            contexto=contexto,
            subscription_id=subscription_id,
            expected_version=expected_version,
            destino=EstadoAssinatura.SUSPENDED,
            event_type="subscription.suspended",
            reason=reason,
        )

    def reativar(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
    ) -> AssinaturaComercial:
        return self._transition(
            contexto=contexto,
            subscription_id=subscription_id,
            expected_version=expected_version,
            destino=EstadoAssinatura.ACTIVE,
            event_type="subscription.reactivated",
            reason="KCA-08 subscription recovery",
        )

    def cancelar(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
        motivo: str,
    ) -> AssinaturaComercial:
        reason = " ".join(motivo.split())
        if not reason:
            raise DadoComercialInvalido("subscription_cancel_reason_required")
        return self._transition(
            contexto=contexto,
            subscription_id=subscription_id,
            expected_version=expected_version,
            destino=EstadoAssinatura.CANCELED,
            event_type="subscription.canceled",
            reason=reason,
        )

    def agendar_cancelamento_fim_periodo(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
    ) -> AssinaturaComercial:
        instante = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioSubscriptionComercialSQLAlchemy(session)
            current = repo.obter(subscription_id.strip())
            if current is None:
                raise RegistroComercialNaoEncontrado("subscription_not_found")
            self._validate_scope(contexto, tenant_id=current.tenant_id)
            if current.status == EstadoAssinatura.CANCELED:
                raise DadoComercialInvalido("subscription_already_canceled")
            if current.cancel_at_period_end:
                return current
            if current.version != expected_version:
                raise DadoComercialInvalido("subscription_expected_version_stale")
            result = repo.atualizar(
                subscription_id=current.subscription_id,
                expected_version=current.version,
                values={"cancel_at_period_end": True},
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.subscription.cancel_scheduled",
                    subscription=result,
                    reason="KCA-08 cancel at period end",
                    instante=instante,
                )
            )
            shared.adicionar_outbox(
                self._event(
                    contexto=contexto,
                    event_type="subscription.cancel_scheduled",
                    subscription=result,
                    instante=instante,
                )
            )
            return result

    def renovar(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
        current_period_start: datetime,
        current_period_end: datetime,
    ) -> AssinaturaComercial:
        start, end = validar_periodo(current_period_start, current_period_end)
        instante = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioSubscriptionComercialSQLAlchemy(session)
            current = repo.obter(subscription_id.strip())
            if current is None:
                raise RegistroComercialNaoEncontrado("subscription_not_found")
            self._validate_scope(contexto, tenant_id=current.tenant_id)
            if current.status != EstadoAssinatura.ACTIVE:
                raise DadoComercialInvalido("subscription_not_active_for_renewal")
            if current.cancel_at_period_end:
                raise DadoComercialInvalido("subscription_cancel_scheduled")
            if (
                current.current_period_start == start
                and current.current_period_end == end
            ):
                return current
            if current.version != expected_version:
                raise DadoComercialInvalido("subscription_expected_version_stale")
            if current.current_period_end is not None and start < utc(
                current.current_period_end
            ):
                raise DadoComercialInvalido("subscription_renewal_overlaps_period")
            result = repo.atualizar(
                subscription_id=current.subscription_id,
                expected_version=current.version,
                values={
                    "current_period_start": start,
                    "current_period_end": end,
                },
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.subscription.renewed",
                    subscription=result,
                    reason="KCA-08 subscription renewal",
                    instante=instante,
                )
            )
            shared.adicionar_outbox(
                self._event(
                    contexto=contexto,
                    event_type="subscription.renewed",
                    subscription=result,
                    instante=instante,
                )
            )
        self._sync_entitlement(
            contexto=contexto,
            subscription=result,
            reason="KCA-08 subscription renewed",
        )
        return result

    def alterar_plano(
        self,
        *,
        contexto: ContextoExecucao,
        subscription_id: str,
        expected_version: int,
        plan_code: str,
        plan_version_id: str,
        price_id: str,
    ) -> AssinaturaComercial:
        instante = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            catalog = RepositorioCatalogoComercialSQLAlchemy(session)
            repo = RepositorioSubscriptionComercialSQLAlchemy(session)
            current = repo.obter(subscription_id.strip())
            if current is None:
                raise RegistroComercialNaoEncontrado("subscription_not_found")
            self._validate_scope(contexto, tenant_id=current.tenant_id)
            if current.status == EstadoAssinatura.CANCELED:
                raise DadoComercialInvalido("subscription_canceled_is_terminal")
            if current.version != expected_version:
                raise DadoComercialInvalido("subscription_expected_version_stale")
            code = normalizar_plan_code(plan_code)
            _, _, _, version, price = self._validate_catalog_binding(
                shared=shared,
                catalog=catalog,
                fm_customer_id=current.fm_customer_id,
                product_account_id=current.product_account_id,
                tenant_id=current.tenant_id,
                plan_code=code,
                plan_version_id=plan_version_id,
                price_id=price_id,
                instante=instante,
            )
            if (
                current.plan_code == code
                and current.plan_version_id == version.plan_version_id
                and current.price_id == price.price_id
            ):
                return current
            result = repo.atualizar(
                subscription_id=current.subscription_id,
                expected_version=current.version,
                values={
                    "plan_code": code,
                    "plan_version_id": version.plan_version_id,
                    "price_id": price.price_id,
                    "currency": price.currency,
                    "billing_period": price.billing_period,
                    "contracted_amount": price.amount,
                },
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.subscription.plan_changed",
                    subscription=result,
                    reason="KCA-08 subscription plan change",
                    instante=instante,
                    metadata={
                        "previous_plan_code": current.plan_code,
                        "previous_plan_version_id": current.plan_version_id,
                        "previous_price_id": current.price_id,
                    },
                )
            )
            shared.adicionar_outbox(
                self._event(
                    contexto=contexto,
                    event_type="subscription.plan_changed",
                    subscription=result,
                    instante=instante,
                )
            )
        self._sync_entitlement(
            contexto=contexto,
            subscription=result,
            reason="KCA-08 subscription plan changed",
        )
        return result
