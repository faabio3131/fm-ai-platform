"""Application boundary do Trial Engine KCA-07."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from core.comercial.catalogo import StatusRegistroCatalogo
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
from core.comercial.modelos import (
    ClasseContaComercial,
    StatusClienteComercial,
    StatusContaProduto,
)
from core.comercial.trial import (
    EstadoTrial,
    TrialComercial,
    calcular_fim_trial,
    utc,
    validar_transicao_trial,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.comercial.catalogo_sqlalchemy import RepositorioCatalogoComercialSQLAlchemy
from infra.comercial.modelos_orm import CommercialAuditORM, CommercialOutboxORM
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy
from infra.comercial.trial_orm import FMCommercialTrialORM
from infra.comercial.trial_sqlalchemy import RepositorioTrialComercialSQLAlchemy


@dataclass(frozen=True, kw_only=True)
class ResultadoAtivacaoTrial:
    trial: TrialComercial
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


class AplicacaoTrialComercialV1:
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

    @staticmethod
    def _actor(contexto: ContextoExecucao) -> str:
        return contexto.identity_user_id or contexto.usuario_id

    @staticmethod
    def _admin_or_system(contexto: ContextoExecucao) -> None:
        if contexto.identidade_sistema:
            return
        if Permissao.ADMIN_ACESSAR not in contexto.permissoes:
            raise PermissionError("seguranca.admin_acesso_exigido")

    @staticmethod
    def _validate_scope(
        contexto: ContextoExecucao,
        *,
        tenant_id: str,
    ) -> None:
        if not contexto.identidade_sistema and contexto.tenant_id != tenant_id:
            raise PermissionError("seguranca.tenant_nao_autorizado")

    @staticmethod
    def _select_trial_plan(
        *,
        catalog: RepositorioCatalogoComercialSQLAlchemy,
        instante: datetime,
    ):
        for plan in catalog.listar_planos(product_code="KORDENA"):
            if plan.status != StatusRegistroCatalogo.CONFIGURED:
                continue
            version = catalog.versao_efetiva_plano(
                plan_id=plan.plan_id,
                instante=instante,
            )
            if version is not None and version.trial_eligible:
                return plan, version
        raise RegistroComercialNaoEncontrado("trial_eligible_plan_not_found")

    def _project(self, snapshot: SnapshotEntitlement) -> None:
        applied = self._entitlement.aplicar_evento_local(
            event_id=f"trial-{snapshot.entitlement_snapshot_id}",
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
            raise RuntimeError("trial_entitlement_projection_not_applied")

    def _sync_entitlement(
        self,
        *,
        contexto: ContextoExecucao,
        trial: TrialComercial,
        reason: str,
    ) -> str:
        now = _now()
        if trial.status == EstadoTrial.ACTIVE:
            if trial.ends_at is None or utc(trial.ends_at) <= now:
                raise DadoComercialInvalido("trial_active_without_future_end")
            state = EstadoComercial.TRIAL_ACTIVE
            plan_code: str | None = trial.plan_code
            valid_until = utc(trial.ends_at)
        elif trial.status == EstadoTrial.EXPIRED:
            state = EstadoComercial.TRIAL_EXPIRED
            plan_code = trial.plan_code
            valid_until = now + self._restricted_lease
        elif trial.status == EstadoTrial.REVOKED:
            state = EstadoComercial.SUSPENDED
            plan_code = trial.plan_code
            valid_until = now + self._restricted_lease
        elif trial.status == EstadoTrial.CONVERTED:
            state = EstadoComercial.CONFIGURATION_PENDING
            plan_code = None
            valid_until = now + self._restricted_lease
        else:
            state = EstadoComercial.TRIAL_PENDING
            plan_code = None
            valid_until = now + self._restricted_lease

        snapshot = self._entitlement.recalcular(
            contexto=contexto,
            idempotency_key=f"trial:{trial.trial_id}:entitlement:v{trial.version}",
            product_account_id=trial.product_account_id,
            tenant_id=trial.tenant_id,
            commercial_state=state,
            plan_code=plan_code,
            valid_until=valid_until,
            change_reason=reason,
        )
        self._project(snapshot)
        return snapshot.entitlement_snapshot_id

    def ativar(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        fm_customer_id: str,
        product_account_id: str,
        tenant_id: str,
        email_verified: bool,
        override_antiabuse: bool = False,
        override_reason: str | None = None,
    ) -> ResultadoAtivacaoTrial:
        key = _key(idempotency_key)
        customer_id = fm_customer_id.strip()
        account_id = product_account_id.strip()
        tenant = tenant_id.strip()
        if not customer_id or not account_id or not tenant:
            raise DadoComercialInvalido("trial_campos_obrigatorios")
        if not email_verified:
            raise DadoComercialInvalido("trial_email_not_verified")
        self._validate_scope(contexto, tenant_id=tenant)
        reason = " ".join((override_reason or "").split()) or None
        if override_antiabuse:
            self._admin_or_system(contexto)
            if reason is None:
                raise DadoComercialInvalido("trial_override_reason_required")

        request_sha256 = _hash_payload(
            {
                "fm_customer_id": customer_id,
                "product_account_id": account_id,
                "tenant_id": tenant,
                "email_verified": True,
                "override_antiabuse": override_antiabuse,
                "override_reason": reason,
            }
        )
        scope = f"trial.activate:{account_id}"
        now = _now()

        try:
            with self._session_factory() as session, session.begin():
                shared = RepositorioComercialSQLAlchemy(session)
                trials = RepositorioTrialComercialSQLAlchemy(session)
                catalog = RepositorioCatalogoComercialSQLAlchemy(session)
                existing_key = shared.obter_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                )
                if existing_key is not None:
                    if existing_key.request_sha256 != request_sha256:
                        raise ConflitoIdempotenciaComercial(
                            "trial_idempotency_payload_conflict"
                        )
                    if existing_key.aggregate_type != "trial":
                        raise ConflitoIdempotenciaComercial(
                            "trial_idempotency_scope_conflict"
                        )
                    existing_trial = trials.obter(str(existing_key.aggregate_id))
                    if existing_trial is None:
                        raise ConflitoIdempotenciaComercial(
                            "trial_idempotency_result_missing"
                        )
                    trial = existing_trial
                else:
                    account = shared.obter_conta_produto(account_id)
                    customer = shared.obter_cliente(customer_id)
                    if account is None:
                        raise RegistroComercialNaoEncontrado(
                            "product_account_not_found"
                        )
                    if customer is None:
                        raise RegistroComercialNaoEncontrado("customer_not_found")
                    if account.fm_customer_id != customer_id:
                        raise DadoComercialInvalido(
                            "trial_customer_product_account_mismatch"
                        )
                    if account.product_code != "KORDENA":
                        raise DadoComercialInvalido("trial_product_not_supported")
                    if account.product_tenant_id != tenant:
                        raise DadoComercialInvalido(
                            "trial_tenant_product_account_mismatch"
                        )
                    if account.status != StatusContaProduto.ACTIVE:
                        raise DadoComercialInvalido(
                            "trial_product_account_not_active"
                        )
                    if customer.status != StatusClienteComercial.ACTIVE:
                        raise DadoComercialInvalido("trial_customer_not_active")

                    if trials.obter_por_product_account(account_id) is not None:
                        raise RegistroComercialDuplicado(
                            "trial_already_exists_for_product_account"
                        )
                    history = trials.listar_por_customer(customer_id)
                    if history and not override_antiabuse:
                        raise RegistroComercialDuplicado(
                            "trial_customer_history_not_eligible"
                        )

                    policy = trials.politica_efetiva(instante=now)
                    if policy is None:
                        raise RegistroComercialNaoEncontrado(
                            "trial_effective_policy_not_found"
                        )
                    plan, plan_version = self._select_trial_plan(
                        catalog=catalog,
                        instante=now,
                    )
                    trial_id = str(uuid4())
                    pending = trials.adicionar(
                        FMCommercialTrialORM(
                            trial_id=trial_id,
                            fm_customer_id=customer_id,
                            product_account_id=account_id,
                            tenant_id=tenant,
                            plan_code=plan.plan_code,
                            plan_version_id=plan_version.plan_version_id,
                            status=EstadoTrial.PENDING.value,
                            policy_version=policy.policy_version,
                            duration_days=policy.duration_days,
                            started_at=None,
                            ends_at=None,
                            converted_at=None,
                            revoked_at=None,
                            override_reason=reason,
                            version=1,
                            correlation_id=contexto.correlation_id,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    validar_transicao_trial(pending.status, EstadoTrial.ACTIVE)
                    end = calcular_fim_trial(
                        started_at=now,
                        duration_days=policy.duration_days,
                    )
                    trial = trials.atualizar(
                        trial_id=pending.trial_id,
                        expected_version=pending.version,
                        values={
                            "status": EstadoTrial.ACTIVE.value,
                            "started_at": now,
                            "ends_at": end,
                        },
                    )
                    shared.adicionar_idempotencia(
                        scope=scope,
                        idempotency_key=key,
                        request_sha256=request_sha256,
                        aggregate_type="trial",
                        aggregate_id=trial.trial_id,
                        created_at=now,
                    )
                    kpi_excluded = customer.account_class == ClasseContaComercial.INTERNAL_TEST
                    shared.adicionar_auditoria(
                        CommercialAuditORM(
                            audit_id=str(uuid4()),
                            actor_user_id=self._actor(contexto),
                            action="commercial.trial.activate",
                            aggregate_type="trial",
                            aggregate_id=trial.trial_id,
                            result="success",
                            reason=reason or "KCA-07 trial activation",
                            correlation_id=contexto.correlation_id,
                            causation_id=contexto.causation_id,
                            metadata_safe={
                                "fm_customer_id": customer_id,
                                "product_account_id": account_id,
                                "tenant_id": tenant,
                                "plan_code": trial.plan_code,
                                "plan_version_id": trial.plan_version_id,
                                "policy_version": trial.policy_version,
                                "duration_days": trial.duration_days,
                                "override_antiabuse": override_antiabuse,
                                "kpi_excluded": kpi_excluded,
                            },
                            timestamp=now,
                        )
                    )
                    for event_type, event_key in (
                        ("trial.created", "created"),
                        ("trial.activated", "activated"),
                    ):
                        shared.adicionar_outbox(
                            CommercialOutboxORM(
                                event_id=str(uuid4()),
                                event_type=event_type,
                                aggregate_type="trial",
                                aggregate_id=trial.trial_id,
                                fm_customer_id=customer_id,
                                product_account_id=account_id,
                                product_code="KORDENA",
                                product_tenant_id=tenant,
                                correlation_id=contexto.correlation_id,
                                causation_id=contexto.causation_id,
                                idempotency_key=f"trial:{trial.trial_id}:{event_key}",
                                occurred_at=now,
                                payload={
                                    "trial_id": trial.trial_id,
                                    "status": trial.status.value,
                                    "fm_customer_id": customer_id,
                                    "product_account_id": account_id,
                                    "tenant_id": tenant,
                                    "plan_code": trial.plan_code,
                                    "plan_version_id": trial.plan_version_id,
                                    "policy_version": trial.policy_version,
                                    "started_at": trial.started_at.isoformat()
                                    if trial.started_at
                                    else None,
                                    "ends_at": trial.ends_at.isoformat()
                                    if trial.ends_at
                                    else None,
                                    "kpi_excluded": kpi_excluded,
                                },
                                version=1,
                                status="pending",
                            )
                        )
        except IntegrityError as exc:
            raise RegistroComercialDuplicado("trial_duplicate") from exc

        snapshot_id = self._sync_entitlement(
            contexto=contexto,
            trial=trial,
            reason="KCA-07 trial active",
        )
        return ResultadoAtivacaoTrial(
            trial=trial,
            entitlement_snapshot_id=snapshot_id,
        )

    def obter_por_product_account(
        self, *, product_account_id: str
    ) -> TrialComercial | None:
        with self._session_factory() as session:
            return RepositorioTrialComercialSQLAlchemy(
                session
            ).obter_por_product_account(product_account_id.strip())

    def marcar_convertido_em_transacao(
        self,
        *,
        session,
        contexto: ContextoExecucao,
        trial_id: str,
        instante: datetime,
        motivo: str = "KCA-08 subscription activation",
    ) -> TrialComercial:
        """Converte o trial dentro da transação coordenada da assinatura.

        Não recalcula entitlement aqui: a ativação da subscription publica o
        estado SUBSCRIPTION_ACTIVE imediatamente após o commit coordenado.
        """
        shared = RepositorioComercialSQLAlchemy(session)
        repo = RepositorioTrialComercialSQLAlchemy(session)
        current = repo.obter(trial_id.strip())
        if current is None:
            raise RegistroComercialNaoEncontrado("trial_not_found")
        self._validate_scope(contexto, tenant_id=current.tenant_id)
        if current.status == EstadoTrial.CONVERTED:
            return current
        validar_transicao_trial(current.status, EstadoTrial.CONVERTED)
        if current.ends_at is not None and instante >= utc(current.ends_at):
            raise DadoComercialInvalido("trial_expired_cannot_convert")
        updated = repo.atualizar(
            trial_id=current.trial_id,
            expected_version=current.version,
            values={
                "status": EstadoTrial.CONVERTED.value,
                "converted_at": instante,
            },
        )
        shared.adicionar_auditoria(
            CommercialAuditORM(
                audit_id=str(uuid4()),
                actor_user_id=self._actor(contexto),
                action="commercial.trial.converted",
                aggregate_type="trial",
                aggregate_id=updated.trial_id,
                result="success",
                reason=motivo[:255],
                correlation_id=contexto.correlation_id,
                causation_id=contexto.causation_id,
                metadata_safe={
                    "product_account_id": updated.product_account_id,
                    "tenant_id": updated.tenant_id,
                    "status": updated.status.value,
                    "coordinated_by": "subscription_engine",
                },
                timestamp=instante,
            )
        )
        shared.adicionar_outbox(
            CommercialOutboxORM(
                event_id=str(uuid4()),
                event_type="trial.converted",
                aggregate_type="trial",
                aggregate_id=updated.trial_id,
                fm_customer_id=updated.fm_customer_id,
                product_account_id=updated.product_account_id,
                product_code="KORDENA",
                product_tenant_id=updated.tenant_id,
                correlation_id=contexto.correlation_id,
                causation_id=contexto.causation_id,
                idempotency_key=(
                    f"trial:{updated.trial_id}:converted:v{updated.version}"
                ),
                occurred_at=instante,
                payload={
                    "trial_id": updated.trial_id,
                    "status": updated.status.value,
                    "product_account_id": updated.product_account_id,
                    "tenant_id": updated.tenant_id,
                },
                version=1,
                status="pending",
            )
        )
        return updated

    def _transition_terminal(
        self,
        *,
        contexto: ContextoExecucao,
        trial_id: str,
        destino: EstadoTrial,
        reason: str,
        instante: datetime,
    ) -> TrialComercial:
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioTrialComercialSQLAlchemy(session)
            current = repo.obter(trial_id.strip())
            if current is None:
                raise RegistroComercialNaoEncontrado("trial_not_found")
            self._validate_scope(contexto, tenant_id=current.tenant_id)
            if current.status == destino:
                return current
            validar_transicao_trial(current.status, destino)
            if (
                destino == EstadoTrial.EXPIRED
                and current.ends_at is not None
                and instante < utc(current.ends_at)
            ):
                raise DadoComercialInvalido("trial_not_expired_yet")
            if (
                destino == EstadoTrial.CONVERTED
                and current.ends_at is not None
                and instante >= utc(current.ends_at)
            ):
                raise DadoComercialInvalido("trial_expired_cannot_convert")
            values: dict[str, object] = {"status": destino.value}
            if destino == EstadoTrial.CONVERTED:
                values["converted_at"] = instante
            if destino == EstadoTrial.REVOKED:
                values["revoked_at"] = instante
            updated = repo.atualizar(
                trial_id=current.trial_id,
                expected_version=current.version,
                values=values,
            )
            shared.adicionar_auditoria(
                CommercialAuditORM(
                    audit_id=str(uuid4()),
                    actor_user_id=self._actor(contexto),
                    action=f"commercial.trial.{destino.value}",
                    aggregate_type="trial",
                    aggregate_id=updated.trial_id,
                    result="success",
                    reason=reason[:255],
                    correlation_id=contexto.correlation_id,
                    causation_id=contexto.causation_id,
                    metadata_safe={
                        "product_account_id": updated.product_account_id,
                        "tenant_id": updated.tenant_id,
                        "status": updated.status.value,
                    },
                    timestamp=instante,
                )
            )
            shared.adicionar_outbox(
                CommercialOutboxORM(
                    event_id=str(uuid4()),
                    event_type=f"trial.{destino.value}",
                    aggregate_type="trial",
                    aggregate_id=updated.trial_id,
                    fm_customer_id=updated.fm_customer_id,
                    product_account_id=updated.product_account_id,
                    product_code="KORDENA",
                    product_tenant_id=updated.tenant_id,
                    correlation_id=contexto.correlation_id,
                    causation_id=contexto.causation_id,
                    idempotency_key=f"trial:{updated.trial_id}:{destino.value}:v{updated.version}",
                    occurred_at=instante,
                    payload={
                        "trial_id": updated.trial_id,
                        "status": updated.status.value,
                        "product_account_id": updated.product_account_id,
                        "tenant_id": updated.tenant_id,
                    },
                    version=1,
                    status="pending",
                )
            )
        self._sync_entitlement(
            contexto=contexto,
            trial=updated,
            reason=reason,
        )
        return updated

    def expirar(
        self,
        *,
        contexto: ContextoExecucao,
        trial_id: str,
        agora: datetime | None = None,
    ) -> TrialComercial:
        instante = utc(agora or _now())
        return self._transition_terminal(
            contexto=contexto,
            trial_id=trial_id,
            destino=EstadoTrial.EXPIRED,
            reason="KCA-07 trial expiration",
            instante=instante,
        )

    def expirar_vencidos(
        self,
        *,
        contexto_factory,
        agora: datetime | None = None,
        limite: int = 500,
    ) -> tuple[TrialComercial, ...]:
        if limite < 1 or limite > 5000:
            raise DadoComercialInvalido("trial_expiration_limit_invalido")
        instante = utc(agora or _now())
        with self._session_factory() as session:
            candidates = RepositorioTrialComercialSQLAlchemy(
                session
            ).listar_expiraveis(instante=instante, limite=limite)
        return tuple(
            self.expirar(
                contexto=contexto_factory(trial),
                trial_id=trial.trial_id,
                agora=instante,
            )
            for trial in candidates
        )

    def revogar(
        self,
        *,
        contexto: ContextoExecucao,
        trial_id: str,
        motivo: str,
    ) -> TrialComercial:
        self._admin_or_system(contexto)
        reason = " ".join(motivo.split())
        if not reason:
            raise DadoComercialInvalido("trial_revoke_reason_required")
        return self._transition_terminal(
            contexto=contexto,
            trial_id=trial_id,
            destino=EstadoTrial.REVOKED,
            reason=reason,
            instante=_now(),
        )

    def marcar_convertido(
        self,
        *,
        contexto: ContextoExecucao,
        trial_id: str,
        motivo: str = "KCA-07 trial conversion",
    ) -> TrialComercial:
        reason = " ".join(motivo.split()) or "KCA-07 trial conversion"
        return self._transition_terminal(
            contexto=contexto,
            trial_id=trial_id,
            destino=EstadoTrial.CONVERTED,
            reason=reason,
            instante=_now(),
        )
