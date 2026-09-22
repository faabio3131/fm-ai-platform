"""Orquestrador da Tenant Provisioning Saga KCA-05."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from core.comercial.entitlement import EstadoComercial, serializar_capabilities
from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
)
from core.comercial.modelos import ClasseContaComercial, StatusContaProduto
from core.comercial.provisioning import (
    EstadoProvisionamento,
    ProvisionamentoKordena,
    validar_transicao,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel
from infra.administracao.repositorio_sqlalchemy import RepositorioAdministracaoSQLAlchemy
from infra.comercial.modelos_orm import CommercialAuditORM, CommercialOutboxORM
from infra.comercial.provisioning_orm import FMCommercialProvisioningSagaORM
from infra.comercial.provisioning_sqlalchemy import RepositorioProvisioningSQLAlchemy
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

SessionFactory = Callable[[], Session]
FailureHook = Callable[[str], None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_key(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 192:
        raise DadoComercialInvalido("idempotency_key_invalida")
    return normalized


def _normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or "@" not in normalized or len(normalized) > 320:
        raise DadoComercialInvalido("email_invalido")
    return normalized


def _request_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AplicacaoProvisioningKordenaV1:
    """Saga persistida, retomável e idempotente para criar um tenant Kordena."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        failure_hook: FailureHook | None = None,
        pending_entitlement_lease_seconds: int = 3600,
    ) -> None:
        if pending_entitlement_lease_seconds < 60:
            raise ValueError("pending_entitlement_lease_seconds_invalido")
        self._session_factory = session_factory
        self._failure_hook = failure_hook
        self._lease = timedelta(seconds=pending_entitlement_lease_seconds)
        self._registry = AplicacaoCommercialRegistryV1(session_factory)
        self._entitlement = AplicacaoEntitlementComercialV1(session_factory)

    def _failpoint(self, step: str) -> None:
        if self._failure_hook is not None:
            self._failure_hook(step)

    @staticmethod
    def _system_context(saga: ProvisionamentoKordena) -> ContextoExecucao:
        return ContextoExecucao.sistema(
            identidade="kordena-provisioning-v1",
            motivo="tenant provisioning saga KCA-05",
            tenant_id=saga.tenant_id,
            unidade_id=saga.unidade_id,
            correlation_id=saga.correlation_id,
            solicitado_em=_now(),
        )

    def _load(self, provisioning_id: str) -> ProvisionamentoKordena:
        with self._session_factory() as session:
            current = RepositorioProvisioningSQLAlchemy(session).obter(
                provisioning_id.strip()
            )
        if current is None:
            raise RegistroComercialNaoEncontrado("provisioning_not_found")
        return current

    def _update(
        self,
        saga: ProvisionamentoKordena,
        **values: object,
    ) -> ProvisionamentoKordena:
        with self._session_factory() as session, session.begin():
            return RepositorioProvisioningSQLAlchemy(session).atualizar(
                provisioning_id=saga.provisioning_id,
                expected_version=saga.version,
                values=dict(values),
            )

    def _transition(
        self,
        saga: ProvisionamentoKordena,
        status: EstadoProvisionamento,
        *,
        current_step: str,
        last_error: str | None = None,
    ) -> ProvisionamentoKordena:
        validar_transicao(saga.status, status)
        return self._update(
            saga,
            status=status.value,
            current_step=current_step,
            last_error=last_error,
        )

    def _emit_once(
        self,
        *,
        saga: ProvisionamentoKordena,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        key = f"provisioning:{saga.provisioning_id}:{event_type}"
        with self._session_factory() as session, session.begin():
            exists = session.scalar(
                select(CommercialOutboxORM.event_id).where(
                    CommercialOutboxORM.event_type == event_type,
                    CommercialOutboxORM.idempotency_key == key,
                )
            )
            if exists is not None:
                return
            session.add(
                CommercialOutboxORM(
                    event_id=str(uuid4()),
                    event_type=event_type,
                    aggregate_type="provisioning",
                    aggregate_id=saga.provisioning_id,
                    fm_customer_id=saga.fm_customer_id,
                    product_account_id=saga.product_account_id,
                    product_code="KORDENA",
                    product_tenant_id=saga.tenant_id,
                    correlation_id=saga.correlation_id,
                    causation_id=None,
                    idempotency_key=key,
                    occurred_at=_now(),
                    payload=payload,
                    version=1,
                    status="pending",
                )
            )

    def solicitar(
        self,
        *,
        idempotency_key: str,
        owner_email: str,
        owner_password: str,
        display_name: str,
        primary_contact_phone: str | None,
        correlation_id: str,
    ) -> ProvisionamentoKordena:
        key = _normalize_key(idempotency_key)
        email = _normalize_email(owner_email)
        name = " ".join(display_name.split())
        if not name or len(name) > 255:
            raise DadoComercialInvalido("display_name_invalido")
        if not owner_password or len(owner_password) > 1024:
            raise DadoComercialInvalido("owner_password_invalida")
        corr = correlation_id.strip()
        if not corr or len(corr) > 128:
            raise DadoComercialInvalido("correlation_id_invalido")
        phone = (
            " ".join(primary_contact_phone.split())
            if primary_contact_phone and primary_contact_phone.strip()
            else None
        )
        payload = {
            "owner_email": email,
            "credential_sha256": hashlib.sha256(
                owner_password.encode("utf-8")
            ).hexdigest(),
            "display_name": name,
            "primary_contact_phone": phone,
        }
        request_sha = _request_hash(payload)

        with self._session_factory() as session, session.begin():
            repo = RepositorioProvisioningSQLAlchemy(session)
            existing = repo.obter_por_idempotencia(key)
            if existing is not None:
                if existing.request_sha256 != request_sha:
                    raise ConflitoIdempotenciaComercial(
                        "provisioning_idempotency_payload_conflict"
                    )
                return existing

            provisioning_id = str(uuid4())
            suffix = provisioning_id.replace("-", "")
            created = repo.adicionar(
                FMCommercialProvisioningSagaORM(
                    provisioning_id=provisioning_id,
                    idempotency_key=key,
                    request_sha256=request_sha,
                    status=EstadoProvisionamento.REQUESTED.value,
                    current_step="requested",
                    fm_customer_id=None,
                    product_account_id=None,
                    identity_user_id=None,
                    membership_id=None,
                    tenant_id=f"krd-{suffix[:24]}",
                    unidade_id=f"unit-{suffix[8:32]}",
                    owner_email=email,
                    display_name=name,
                    primary_contact_phone=phone,
                    trial_binding_status="pending_kca07",
                    entitlement_snapshot_id=None,
                    attempts=0,
                    last_error=None,
                    version=1,
                    correlation_id=corr,
                    created_at=_now(),
                    updated_at=_now(),
                )
            )

        self._emit_once(
            saga=created,
            event_type="tenant.provisioning_requested",
            payload={
                "provisioning_id": created.provisioning_id,
                "tenant_id": created.tenant_id,
                "unidade_id": created.unidade_id,
            },
        )
        return created

    def _ensure_customer(
        self, saga: ProvisionamentoKordena
    ) -> ProvisionamentoKordena:
        if saga.fm_customer_id is not None:
            return saga
        self._failpoint("customer")
        customer = self._registry.criar_cliente(
            contexto=self._system_context(saga),
            idempotency_key=f"{saga.idempotency_key}:customer",
            display_name=saga.display_name,
            legal_name=None,
            account_class=ClasseContaComercial.TRIAL,
            primary_contact_email=saga.owner_email,
            primary_contact_phone=saga.primary_contact_phone,
        )
        return self._update(
            saga,
            fm_customer_id=customer.fm_customer_id,
            current_step="customer_created",
        )

    def _ensure_product_account(
        self, saga: ProvisionamentoKordena
    ) -> ProvisionamentoKordena:
        if saga.product_account_id is None:
            self._failpoint("product_account")
            account = self._registry.criar_conta_produto(
                contexto=self._system_context(saga),
                idempotency_key=f"{saga.idempotency_key}:product-account",
                fm_customer_id=str(saga.fm_customer_id),
                product_code="KORDENA",
                product_tenant_id=None,
            )
            saga = self._update(
                saga,
                product_account_id=account.product_account_id,
                current_step="product_account_created",
            )
        account = self._registry.obter_conta_produto(
            product_account_id=str(saga.product_account_id)
        )
        if account.status == StatusContaProduto.REQUESTED:
            self._failpoint("product_account_provisioning")
            account = self._registry.transicionar_conta_produto(
                contexto=self._system_context(saga),
                product_account_id=account.product_account_id,
                expected_version=account.version,
                status=StatusContaProduto.PROVISIONING,
                product_tenant_id=saga.tenant_id,
            )
        if account.product_tenant_id != saga.tenant_id:
            raise RegistroComercialDuplicado("provisioning_tenant_binding_conflict")
        return self._update(saga, current_step="product_account_provisioning")

    def _ensure_identity(
        self,
        saga: ProvisionamentoKordena,
        password: str,
    ) -> ProvisionamentoKordena:
        if saga.identity_user_id is not None and saga.membership_id is not None:
            return saga
        self._failpoint("identity_membership")
        with self._session_factory() as session, session.begin():
            repo = RepositorioIdentidadesSQLAlchemy(session)
            current = repo.obter_por_email(saga.owner_email)
            if current is None:
                if not password:
                    raise DadoComercialInvalido(
                        "owner_password_required_for_identity"
                    )
                current = repo.criar_usuario(
                    email=saga.owner_email,
                    password=password,
                    tenant_id=saga.tenant_id,
                    unidade_padrao_id=saga.unidade_id,
                    papeis=(Papel.ADMINISTRADOR,),
                    unidades_permitidas=(saga.unidade_id,),
                    acesso_admin_sensivel=True,
                )
            else:
                memberships = repo.listar_memberships(
                    identity_user_id=str(current.global_identity_id)
                )
                same_scope = next(
                    (
                        item
                        for item in memberships
                        if item.product_code == "KORDENA"
                        and item.tenant_id == saga.tenant_id
                    ),
                    None,
                )
                if same_scope is None:
                    current = repo.criar_membership_existente(
                        identity_user_id=str(current.global_identity_id),
                        tenant_id=saga.tenant_id,
                        unidade_padrao_id=saga.unidade_id,
                        papeis=(Papel.ADMINISTRADOR,),
                        unidades_permitidas=(saga.unidade_id,),
                        acesso_admin_sensivel=True,
                    )
                else:
                    current = same_scope
        return self._update(
            saga,
            identity_user_id=current.global_identity_id,
            membership_id=current.membership_subject_id,
            current_step="identity_membership_created",
        )

    def _ensure_admin_scope(
        self, saga: ProvisionamentoKordena
    ) -> ProvisionamentoKordena:
        self._failpoint("admin_scope")
        with self._session_factory() as session, session.begin():
            RepositorioAdministracaoSQLAlchemy(session).garantir_escopo(
                tenant_id=saga.tenant_id,
                unidade_id=saga.unidade_id,
                nome_empresa=saga.display_name,
                nome_unidade=saga.display_name,
            )
        return self._update(
            saga,
            current_step="tenant_company_unit_created",
        )

    def _activate_account(
        self, saga: ProvisionamentoKordena
    ) -> ProvisionamentoKordena:
        self._failpoint("activate_product_account")
        account = self._registry.obter_conta_produto(
            product_account_id=str(saga.product_account_id)
        )
        if account.status != StatusContaProduto.ACTIVE:
            account = self._registry.transicionar_conta_produto(
                contexto=self._system_context(saga),
                product_account_id=account.product_account_id,
                expected_version=account.version,
                status=StatusContaProduto.ACTIVE,
                product_tenant_id=saga.tenant_id,
            )
        return self._update(saga, current_step="product_account_active")

    def _ensure_pending_entitlement(
        self, saga: ProvisionamentoKordena
    ) -> ProvisionamentoKordena:
        if saga.entitlement_snapshot_id is not None:
            return saga
        self._failpoint("entitlement")
        snapshot = self._entitlement.recalcular(
            contexto=self._system_context(saga),
            idempotency_key=f"{saga.idempotency_key}:pending-entitlement",
            product_account_id=str(saga.product_account_id),
            tenant_id=saga.tenant_id,
            commercial_state=EstadoComercial.TRIAL_PENDING,
            plan_code=None,
            valid_until=_now() + self._lease,
            change_reason="KCA-05 provisioning pending KCA-07 trial activation",
        )
        applied = self._entitlement.aplicar_evento_local(
            event_id=f"prov-{saga.provisioning_id}",
            payload={
                "product_account_id": snapshot.product_account_id,
                "tenant_id": snapshot.tenant_id,
                "revision": snapshot.revision,
                "commercial_state": snapshot.commercial_state.value,
                "plan_code": snapshot.plan_code,
                "plan_version_id": snapshot.plan_version_id,
                "access_mode": snapshot.access_mode.value,
                "capabilities": serializar_capabilities(
                    snapshot.capabilities
                ),
                "effective_from": snapshot.effective_from.isoformat(),
                "valid_until": snapshot.valid_until.isoformat(),
            },
        )
        if not applied:
            decision = self._entitlement.avaliar_local(
                tenant_id=saga.tenant_id,
                product_account_id=str(saga.product_account_id),
            )
            if decision.revision is None or decision.revision < snapshot.revision:
                raise RuntimeError("entitlement_projection_not_applied")
        return self._update(
            saga,
            entitlement_snapshot_id=snapshot.entitlement_snapshot_id,
            current_step="pending_entitlement_projected",
        )

    def _mark_failed(
        self,
        saga: ProvisionamentoKordena,
        exc: Exception,
    ) -> None:
        current = self._load(saga.provisioning_id)
        if current.status in {
            EstadoProvisionamento.READY,
            EstadoProvisionamento.COMPENSATED,
        }:
            return
        if current.status not in {
            EstadoProvisionamento.VALIDATING,
            EstadoProvisionamento.PROVISIONING,
            EstadoProvisionamento.COMPENSATING,
        }:
            return
        failed = self._transition(
            current,
            EstadoProvisionamento.FAILED_RETRYABLE,
            current_step=current.current_step,
            last_error=f"{type(exc).__name__}:{str(exc)[:300]}",
        )
        self._emit_once(
            saga=failed,
            event_type="tenant.provisioning_failed",
            payload={
                "provisioning_id": failed.provisioning_id,
                "tenant_id": failed.tenant_id,
                "step": failed.current_step,
                "retryable": True,
            },
        )

    def executar(
        self,
        *,
        provisioning_id: str,
        owner_password: str,
    ) -> ProvisionamentoKordena:
        saga = self._load(provisioning_id)
        if saga.status == EstadoProvisionamento.READY:
            return saga
        if saga.status == EstadoProvisionamento.COMPENSATED:
            raise DadoComercialInvalido("provisioning_already_compensated")
        if saga.status in {
            EstadoProvisionamento.REQUESTED,
            EstadoProvisionamento.FAILED_RETRYABLE,
        }:
            saga = self._transition(
                saga,
                EstadoProvisionamento.VALIDATING,
                current_step="validating",
                last_error=None,
            )
        saga = self._update(saga, attempts=saga.attempts + 1)
        try:
            self._failpoint("validating")
            if saga.status == EstadoProvisionamento.VALIDATING:
                saga = self._transition(
                    saga,
                    EstadoProvisionamento.PROVISIONING,
                    current_step="provisioning",
                )
            saga = self._ensure_customer(saga)
            saga = self._ensure_product_account(saga)
            saga = self._ensure_identity(saga, owner_password)
            saga = self._ensure_admin_scope(saga)
            saga = self._activate_account(saga)
            saga = self._ensure_pending_entitlement(saga)
            self._failpoint("ready")
            saga = self._transition(
                saga,
                EstadoProvisionamento.READY,
                current_step="ready",
            )
            self._emit_once(
                saga=saga,
                event_type="tenant.provisioned",
                payload={
                    "provisioning_id": saga.provisioning_id,
                    "fm_customer_id": saga.fm_customer_id,
                    "product_account_id": saga.product_account_id,
                    "tenant_id": saga.tenant_id,
                    "unidade_id": saga.unidade_id,
                    "identity_user_id": saga.identity_user_id,
                    "membership_id": saga.membership_id,
                    "trial_binding_status": saga.trial_binding_status,
                    "entitlement_snapshot_id": saga.entitlement_snapshot_id,
                },
            )
            with self._session_factory() as session, session.begin():
                session.add(
                    CommercialAuditORM(
                        audit_id=str(uuid4()),
                        actor_user_id="kordena-provisioning-v1",
                        action="commercial.tenant.provisioned",
                        aggregate_type="provisioning",
                        aggregate_id=saga.provisioning_id,
                        result="success",
                        reason="KCA-05 tenant provisioning saga",
                        correlation_id=saga.correlation_id,
                        causation_id=None,
                        metadata_safe={
                            "tenant_id": saga.tenant_id,
                            "product_account_id": saga.product_account_id,
                            "attempts": saga.attempts,
                        },
                        timestamp=_now(),
                    )
                )
            return saga
        except Exception as exc:
            self._mark_failed(saga, exc)
            raise

    def compensar(
        self,
        *,
        provisioning_id: str,
        motivo: str,
    ) -> ProvisionamentoKordena:
        saga = self._load(provisioning_id)
        if saga.status == EstadoProvisionamento.COMPENSATED:
            return saga
        if saga.status == EstadoProvisionamento.READY:
            raise DadoComercialInvalido(
                "provisioning_ready_requires_lifecycle_command"
            )
        saga = self._transition(
            saga,
            EstadoProvisionamento.COMPENSATING,
            current_step="compensating",
            last_error=motivo.strip()[:300] or "manual_compensation",
        )
        try:
            if saga.product_account_id is not None:
                account = self._registry.obter_conta_produto(
                    product_account_id=saga.product_account_id
                )
                if account.status != StatusContaProduto.CLOSED:
                    self._registry.transicionar_conta_produto(
                        contexto=self._system_context(saga),
                        product_account_id=account.product_account_id,
                        expected_version=account.version,
                        status=StatusContaProduto.CLOSED,
                        product_tenant_id=saga.tenant_id,
                    )
            saga = self._transition(
                saga,
                EstadoProvisionamento.COMPENSATED,
                current_step="compensated",
            )
            self._emit_once(
                saga=saga,
                event_type="tenant.provisioning_compensated",
                payload={
                    "provisioning_id": saga.provisioning_id,
                    "tenant_id": saga.tenant_id,
                    "reason": motivo.strip()[:200],
                },
            )
            return saga
        except Exception as exc:
            self._mark_failed(saga, exc)
            raise

    def registrar_evento(
        self,
        *,
        event_id: str,
        provisioning_id: str,
        event_type: str,
    ) -> bool:
        with self._session_factory() as session, session.begin():
            return RepositorioProvisioningSQLAlchemy(
                session
            ).registrar_evento_recebido(
                event_id=event_id.strip(),
                provisioning_id=provisioning_id.strip(),
                event_type=event_type.strip(),
            )
