"""Aplicação de configuração multi-provider e recebimentos — KCA-09B."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from application.commercial_billing import (
    BillingGatewayV1,
    BillingProviderAdapterRegistryV1,
    BillingProviderBinding,
)
from core.comercial.billing import BillingCallContext, BillingProviderError
from core.comercial.billing_config import (
    BillingConnectionTestStatus,
    BillingEnvironment,
    BillingPaymentMethod,
    BillingProviderAccount,
    BillingProviderAccountStatus,
    BillingRouteAccount,
    BillingRouteDecision,
    BillingRoutingPolicy,
    normalizar_payment_methods,
    normalizar_provider_code,
    normalizar_secret_reference,
    validar_transicao_provider_account,
)
from core.comercial.erros import (
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
)
from core.comercial.modelos import normalizar_product_code
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.erros import ReferenciaSegredoInvalida, SegredoAusente
from core.seguranca.segredos import SecretStore
from infra.comercial.billing_config_orm import (
    FMBillingProviderAccountORM,
    FMBillingRoutingPolicyORM,
)
from infra.comercial.billing_config_sqlalchemy import RepositorioBillingConfigSQLAlchemy
from infra.comercial.modelos_orm import CommercialAuditORM
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy
from infra.seguranca.segredos_orm import SegredoIntegracaoORM
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore

SessionFactory = Callable[[], Session]


@dataclass(frozen=True, kw_only=True)
class BillingConnectionTestOutcome:
    account: BillingProviderAccount
    ok: bool
    detail_code: str


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


def _clean(value: str, *, field: str, max_length: int) -> str:
    result = " ".join(value.split())
    if not result or len(result) > max_length:
        raise DadoComercialInvalido(f"billing_{field}_invalido")
    return result


def _optional(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    result = " ".join(value.split())
    if not result:
        return None
    if len(result) > max_length:
        raise DadoComercialInvalido("billing_campo_excede_limite")
    return result


def _safe_detail_code(value: str, *, fallback: str) -> str:
    code = value.strip()
    if (
        not code
        or len(code) > 128
        or not all(char.isalnum() or char in {"_", "-", "."} for char in code)
    ):
        return fallback
    return code


class AplicacaoBillingConfigurationV1:
    @staticmethod
    def _validar_vault_scope(
        *,
        session: Session,
        contexto: ContextoExecucao,
        reference: str | None,
    ) -> None:
        if not reference or not reference.startswith("vault:"):
            return
        row = session.get(SegredoIntegracaoORM, reference)
        if (
            row is None
            or row.tenant_id != contexto.tenant_id
            or row.unidade_id != contexto.unidade_id
        ):
            raise PermissionError("billing.secret_reference_scope_mismatch")

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        adapter_registry: BillingProviderAdapterRegistryV1,
        secret_store: SecretStore,
    ) -> None:
        self._session_factory = session_factory
        self._adapter_registry = adapter_registry
        self._secret_store = secret_store

    @staticmethod
    def _actor(contexto: ContextoExecucao) -> str:
        return contexto.identity_user_id or contexto.usuario_id

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
            actor_user_id=AplicacaoBillingConfigurationV1._actor(contexto),
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

    def criar_provider_account(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        provider_code: str,
        display_name: str,
        legal_entity_ref: str | None,
        environment: BillingEnvironment,
        credential_secret_reference: str | None,
        supported_payment_methods: tuple[BillingPaymentMethod, ...],
        supports_recurring: bool,
        supports_webhooks: bool,
        priority: int = 100,
    ) -> BillingProviderAccount:
        key = _key(idempotency_key)
        code = normalizar_provider_code(provider_code)
        name = _clean(display_name, field="display_name", max_length=128)
        legal_ref = _optional(legal_entity_ref, max_length=128)
        secret_ref = (
            normalizar_secret_reference(credential_secret_reference)
            if credential_secret_reference
            else None
        )
        methods = normalizar_payment_methods(supported_payment_methods)
        if priority < 0 or priority > 100000:
            raise DadoComercialInvalido("billing_priority_invalida")
        payload = {
            "provider_code": code,
            "display_name": name,
            "legal_entity_ref": legal_ref,
            "environment": environment.value,
            "credential_secret_reference": secret_ref,
            "supported_payment_methods": [item.value for item in methods],
            "supports_recurring": supports_recurring,
            "supports_webhooks": supports_webhooks,
            "priority": priority,
        }
        request_sha256 = _hash_payload(payload)
        scope = "billing.provider_account.create"
        instante = _now()

        try:
            with self._session_factory() as session, session.begin():
                shared = RepositorioComercialSQLAlchemy(session)
                repo = RepositorioBillingConfigSQLAlchemy(session)
                self._validar_vault_scope(
                    session=session,
                    contexto=contexto,
                    reference=secret_ref,
                )
                existing = shared.obter_idempotencia(
                    scope=scope, idempotency_key=key
                )
                if existing is not None:
                    if existing.request_sha256 != request_sha256:
                        raise ConflitoIdempotenciaComercial(
                            "billing_provider_account_idempotency_payload_conflict"
                        )
                    if existing.aggregate_type != "billing_provider_account":
                        raise ConflitoIdempotenciaComercial(
                            "billing_provider_account_idempotency_scope_conflict"
                        )
                    account = repo.obter_provider_account(existing.aggregate_id)
                    if account is None:
                        raise ConflitoIdempotenciaComercial(
                            "billing_provider_account_idempotency_result_missing"
                        )
                    return account

                account_id = str(uuid4())
                account = repo.adicionar_provider_account(
                    FMBillingProviderAccountORM(
                        provider_account_id=account_id,
                        provider_code=code,
                        display_name=name,
                        legal_entity_ref=legal_ref,
                        environment=environment.value,
                        status=BillingProviderAccountStatus.DRAFT.value,
                        credential_secret_reference=secret_ref,
                        supported_payment_methods=[item.value for item in methods],
                        supports_recurring=supports_recurring,
                        supports_webhooks=supports_webhooks,
                        priority=priority,
                        last_tested_at=None,
                        last_test_status=BillingConnectionTestStatus.NEVER.value,
                        correlation_id=contexto.correlation_id,
                        created_by=self._actor(contexto),
                        updated_by=self._actor(contexto),
                        version=1,
                        created_at=instante,
                        updated_at=instante,
                    )
                )
                shared.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="billing_provider_account",
                    aggregate_id=account_id,
                    created_at=instante,
                )
                shared.adicionar_auditoria(
                    self._audit(
                        contexto=contexto,
                        action="commercial.billing.provider_account.create",
                        aggregate_type="billing_provider_account",
                        aggregate_id=account_id,
                        result="success",
                        reason="kca09b_provider_account_create",
                        metadata_safe={
                            "provider_code": code,
                            "environment": environment.value,
                            "status": account.status.value,
                            "payment_methods": [item.value for item in methods],
                            "supports_recurring": supports_recurring,
                            "supports_webhooks": supports_webhooks,
                        },
                        instante=instante,
                    )
                )
                return account
        except IntegrityError as exc:
            raise RegistroComercialDuplicado(
                "billing_provider_account_duplicate"
            ) from exc

    def obter_provider_account(
        self, *, provider_account_id: str
    ) -> BillingProviderAccount:
        with self._session_factory() as session:
            account = RepositorioBillingConfigSQLAlchemy(
                session
            ).obter_provider_account(provider_account_id.strip())
        if account is None:
            raise RegistroComercialNaoEncontrado(
                "billing_provider_account_not_found"
            )
        return account

    def listar_provider_accounts(self) -> tuple[BillingProviderAccount, ...]:
        with self._session_factory() as session:
            return RepositorioBillingConfigSQLAlchemy(
                session
            ).listar_provider_accounts()

    def atualizar_provider_account(
        self,
        *,
        contexto: ContextoExecucao,
        provider_account_id: str,
        expected_version: int,
        display_name: str,
        legal_entity_ref: str | None,
        credential_secret_reference: str | None,
        supported_payment_methods: tuple[BillingPaymentMethod, ...],
        supports_recurring: bool,
        supports_webhooks: bool,
        priority: int,
    ) -> BillingProviderAccount:
        account_id = provider_account_id.strip()
        name = _clean(display_name, field="display_name", max_length=128)
        legal_ref = _optional(legal_entity_ref, max_length=128)
        requested_secret_ref = (
            normalizar_secret_reference(credential_secret_reference)
            if credential_secret_reference
            else None
        )
        methods = normalizar_payment_methods(supported_payment_methods)
        if priority < 0 or priority > 100000:
            raise DadoComercialInvalido("billing_priority_invalida")
        instante = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioBillingConfigSQLAlchemy(session)
            current = repo.obter_provider_account(account_id)
            if current is None:
                raise RegistroComercialNaoEncontrado(
                    "billing_provider_account_not_found"
                )
            if current.status == BillingProviderAccountStatus.DISABLED:
                raise DadoComercialInvalido(
                    "billing_provider_account_disabled_is_terminal"
                )
            self._validar_vault_scope(
                session=session,
                contexto=contexto,
                reference=requested_secret_ref,
            )
            updated = repo.atualizar_provider_account(
                provider_account_id=account_id,
                expected_version=expected_version,
                values={
                    "display_name": name,
                    "legal_entity_ref": legal_ref,
                    "credential_secret_reference": (
                        requested_secret_ref
                        if requested_secret_ref is not None
                        else current.credential_secret_reference
                    ),
                    "supported_payment_methods": [item.value for item in methods],
                    "supports_recurring": supports_recurring,
                    "supports_webhooks": supports_webhooks,
                    "priority": priority,
                    "status": BillingProviderAccountStatus.VALIDATING.value,
                    "last_test_status": BillingConnectionTestStatus.NEVER.value,
                    "last_tested_at": None,
                    "correlation_id": contexto.correlation_id,
                    "updated_by": self._actor(contexto),
                },
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.provider_account.update",
                    aggregate_type="billing_provider_account",
                    aggregate_id=account_id,
                    result="success",
                    reason="kca09b_provider_account_update_requires_revalidation",
                    metadata_safe={
                        "provider_code": updated.provider_code,
                        "environment": updated.environment.value,
                        "status": updated.status.value,
                        "payment_methods": [
                            item.value for item in updated.supported_payment_methods
                        ],
                        "version": updated.version,
                    },
                    instante=instante,
                )
            )
            return updated

    def armazenar_credencial(
        self,
        *,
        contexto: ContextoExecucao,
        provider_account_id: str,
        expected_version: int,
        credential_value: str,
    ) -> BillingProviderAccount:
        account_id = provider_account_id.strip()
        secret = credential_value.strip()
        if not secret or len(secret) > 16384:
            raise DadoComercialInvalido("billing_credential_value_invalido")
        instante = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioBillingConfigSQLAlchemy(session)
            current = repo.obter_provider_account(account_id)
            if current is None:
                raise RegistroComercialNaoEncontrado(
                    "billing_provider_account_not_found"
                )
            if current.status == BillingProviderAccountStatus.DISABLED:
                raise DadoComercialInvalido(
                    "billing_provider_account_disabled_is_terminal"
                )
            vault = EncryptedSQLAlchemySecretStore(session)
            reference = vault.armazenar(
                contexto=contexto,
                provedor=current.provider_code,
                finalidade=f"fm_billing_account:{account_id}",
                valor=secret,
            )
            updated = repo.atualizar_provider_account(
                provider_account_id=account_id,
                expected_version=expected_version,
                values={
                    "credential_secret_reference": reference,
                    "status": BillingProviderAccountStatus.VALIDATING.value,
                    "last_test_status": BillingConnectionTestStatus.NEVER.value,
                    "last_tested_at": None,
                    "correlation_id": contexto.correlation_id,
                    "updated_by": self._actor(contexto),
                },
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.provider_account.credential.rotate",
                    aggregate_type="billing_provider_account",
                    aggregate_id=account_id,
                    result="success",
                    reason="kca09b_encrypted_vault_rotation",
                    metadata_safe={
                        "provider_code": updated.provider_code,
                        "environment": updated.environment.value,
                        "credential_reference_type": "vault",
                        "status": updated.status.value,
                        "version": updated.version,
                    },
                    instante=instante,
                )
            )
            return updated

    def testar_conexao(
        self,
        *,
        contexto: ContextoExecucao,
        provider_account_id: str,
        expected_version: int,
        timeout_seconds: float = 10.0,
    ) -> BillingConnectionTestOutcome:
        account_id = provider_account_id.strip()
        instante = _now()
        with self._session_factory() as session, session.begin():
            repo = RepositorioBillingConfigSQLAlchemy(session)
            current = repo.obter_provider_account(account_id)
            if current is None:
                raise RegistroComercialNaoEncontrado(
                    "billing_provider_account_not_found"
                )
            if current.status == BillingProviderAccountStatus.DISABLED:
                raise DadoComercialInvalido(
                    "billing_provider_account_disabled_is_terminal"
                )
            validating = repo.atualizar_provider_account(
                provider_account_id=account_id,
                expected_version=expected_version,
                values={
                    "status": BillingProviderAccountStatus.VALIDATING.value,
                    "last_test_status": BillingConnectionTestStatus.NEVER.value,
                    "correlation_id": contexto.correlation_id,
                    "updated_by": self._actor(contexto),
                },
            )

        detail_code = "connection_ok"
        ok = False
        try:
            if not validating.credential_secret_reference:
                raise DadoComercialInvalido(
                    "billing_credential_not_configured"
                )
            provider = self._adapter_registry.resolve(validating.provider_code)
            binding = BillingProviderBinding(
                provider_code=validating.provider_code,
                credential_secret_reference=validating.credential_secret_reference,
            )
            call_context = BillingCallContext(
                idempotency_key=(
                    f"billing-connection-test:{account_id}:v{validating.version}"
                ),
                correlation_id=contexto.correlation_id,
                timeout_seconds=timeout_seconds,
            )
            if validating.credential_secret_reference.startswith("vault:"):
                with self._session_factory() as secret_session:
                    vault = EncryptedSQLAlchemySecretStore(secret_session)
                    if not vault.pertence_ao_escopo(
                        contexto=contexto,
                        reference=validating.credential_secret_reference,
                    ):
                        raise PermissionError(
                            "billing.secret_reference_scope_mismatch"
                        )
                    gateway = BillingGatewayV1(
                        provider=provider,
                        binding=binding,
                        secret_store=vault,
                    )
                    result = gateway.test_connection(context=call_context)
            else:
                gateway = BillingGatewayV1(
                    provider=provider,
                    binding=binding,
                    secret_store=self._secret_store,
                )
                result = gateway.test_connection(context=call_context)
            ok = bool(result.ok)
            if normalizar_provider_code(result.provider_code) != validating.provider_code:
                raise DadoComercialInvalido(
                    "billing_connection_provider_mismatch"
                )
            detail_code = _safe_detail_code(
                result.detail_code,
                fallback="connection_ok" if ok else "connection_failed",
            )
        except (
            BillingProviderError,
            DadoComercialInvalido,
            ReferenciaSegredoInvalida,
            SegredoAusente,
            RuntimeError,
            PermissionError,
        ) as exc:
            detail_code = type(exc).__name__
            ok = False

        final_status = (
            BillingConnectionTestStatus.PASS
            if ok
            else BillingConnectionTestStatus.FAIL
        )
        tested_at = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioBillingConfigSQLAlchemy(session)
            account = repo.atualizar_provider_account(
                provider_account_id=account_id,
                expected_version=validating.version,
                values={
                    "last_test_status": final_status.value,
                    "last_tested_at": tested_at,
                    "correlation_id": contexto.correlation_id,
                    "updated_by": self._actor(contexto),
                },
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.provider_account.test_connection",
                    aggregate_type="billing_provider_account",
                    aggregate_id=account_id,
                    result="success" if ok else "failed",
                    reason=detail_code,
                    metadata_safe={
                        "provider_code": account.provider_code,
                        "environment": account.environment.value,
                        "test_status": account.last_test_status.value,
                    },
                    instante=tested_at,
                )
            )
        return BillingConnectionTestOutcome(
            account=account,
            ok=ok,
            detail_code=detail_code,
        )

    def transicionar_provider_account(
        self,
        *,
        contexto: ContextoExecucao,
        provider_account_id: str,
        expected_version: int,
        status: BillingProviderAccountStatus,
    ) -> BillingProviderAccount:
        account_id = provider_account_id.strip()
        instante = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioBillingConfigSQLAlchemy(session)
            current = repo.obter_provider_account(account_id)
            if current is None:
                raise RegistroComercialNaoEncontrado(
                    "billing_provider_account_not_found"
                )
            validar_transicao_provider_account(
                current.status,
                status,
                last_test_status=current.last_test_status,
            )
            updated = repo.atualizar_provider_account(
                provider_account_id=account_id,
                expected_version=expected_version,
                values={
                    "status": status.value,
                    "correlation_id": contexto.correlation_id,
                    "updated_by": self._actor(contexto),
                },
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.provider_account.transition",
                    aggregate_type="billing_provider_account",
                    aggregate_id=account_id,
                    result="success",
                    reason="kca09b_provider_account_transition",
                    metadata_safe={
                        "provider_code": updated.provider_code,
                        "previous_status": current.status.value,
                        "new_status": updated.status.value,
                        "version": updated.version,
                    },
                    instante=instante,
                )
            )
            return updated

    @staticmethod
    def _validar_route_accounts(
        *,
        repo: RepositorioBillingConfigSQLAlchemy,
        account_ids: tuple[str, ...],
        payment_method: BillingPaymentMethod,
        environment: BillingEnvironment,
        requires_recurring: bool,
        requires_webhooks: bool,
    ) -> tuple[BillingProviderAccount, ...]:
        if len(account_ids) != len(set(account_ids)):
            raise DadoComercialInvalido("billing_routing_account_duplicate")
        accounts: list[BillingProviderAccount] = []
        for account_id in account_ids:
            account = repo.obter_provider_account(account_id)
            if account is None:
                raise RegistroComercialNaoEncontrado(
                    "billing_routing_provider_account_not_found"
                )
            if account.status != BillingProviderAccountStatus.ACTIVE:
                raise DadoComercialInvalido(
                    "billing_routing_provider_account_not_active"
                )
            if account.environment != environment:
                raise DadoComercialInvalido(
                    "billing_routing_environment_mismatch"
                )
            if payment_method not in account.supported_payment_methods:
                raise DadoComercialInvalido(
                    "billing_routing_payment_method_not_supported"
                )
            if requires_recurring and not account.supports_recurring:
                raise DadoComercialInvalido(
                    "billing_routing_recurring_not_supported"
                )
            if requires_webhooks and not account.supports_webhooks:
                raise DadoComercialInvalido(
                    "billing_routing_webhooks_not_supported"
                )
            accounts.append(account)
        return tuple(accounts)

    def criar_routing_policy(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        product_code: str,
        payment_method: BillingPaymentMethod,
        environment: BillingEnvironment,
        primary_provider_account_id: str,
        fallback_provider_account_ids: tuple[str, ...] = (),
        requires_recurring: bool = False,
        requires_webhooks: bool = False,
    ) -> BillingRoutingPolicy:
        key = _key(idempotency_key)
        product = normalizar_product_code(product_code)
        primary = primary_provider_account_id.strip()
        fallbacks = tuple(item.strip() for item in fallback_provider_account_ids)
        if not primary or any(not item for item in fallbacks):
            raise DadoComercialInvalido("billing_routing_account_id_invalido")
        ordered = (primary, *fallbacks)
        request_sha256 = _hash_payload(
            {
                "product_code": product,
                "payment_method": payment_method.value,
                "environment": environment.value,
                "requires_recurring": requires_recurring,
                "requires_webhooks": requires_webhooks,
                "primary_provider_account_id": primary,
                "fallback_provider_account_ids": fallbacks,
            }
        )
        scope = (
            f"billing.routing.create:{product}:"
            f"{payment_method.value}:{environment.value}"
        )
        instante = _now()
        try:
            with self._session_factory() as session, session.begin():
                shared = RepositorioComercialSQLAlchemy(session)
                repo = RepositorioBillingConfigSQLAlchemy(session)
                existing = shared.obter_idempotencia(
                    scope=scope, idempotency_key=key
                )
                if existing is not None:
                    if existing.request_sha256 != request_sha256:
                        raise ConflitoIdempotenciaComercial(
                            "billing_routing_idempotency_payload_conflict"
                        )
                    policy = repo.obter_routing_policy(existing.aggregate_id)
                    if policy is None:
                        raise ConflitoIdempotenciaComercial(
                            "billing_routing_idempotency_result_missing"
                        )
                    return policy
                if (
                    repo.obter_routing_policy_scope(
                        product_code=product,
                        payment_method=payment_method,
                        environment=environment,
                    )
                    is not None
                ):
                    raise RegistroComercialDuplicado(
                        "billing_routing_scope_duplicate"
                    )
                self._validar_route_accounts(
                    repo=repo,
                    account_ids=ordered,
                    payment_method=payment_method,
                    environment=environment,
                    requires_recurring=requires_recurring,
                    requires_webhooks=requires_webhooks,
                )
                policy_id = str(uuid4())
                policy = repo.adicionar_routing_policy(
                    FMBillingRoutingPolicyORM(
                        routing_policy_id=policy_id,
                        product_code=product,
                        payment_method=payment_method.value,
                        environment=environment.value,
                        requires_recurring=requires_recurring,
                        requires_webhooks=requires_webhooks,
                        primary_provider_account_id=primary,
                        fallback_provider_account_ids=list(fallbacks),
                        active=True,
                        correlation_id=contexto.correlation_id,
                        created_by=self._actor(contexto),
                        updated_by=self._actor(contexto),
                        version=1,
                        created_at=instante,
                        updated_at=instante,
                    )
                )
                shared.adicionar_idempotencia(
                    scope=scope,
                    idempotency_key=key,
                    request_sha256=request_sha256,
                    aggregate_type="billing_routing_policy",
                    aggregate_id=policy_id,
                    created_at=instante,
                )
                shared.adicionar_auditoria(
                    self._audit(
                        contexto=contexto,
                        action="commercial.billing.routing_policy.create",
                        aggregate_type="billing_routing_policy",
                        aggregate_id=policy_id,
                        result="success",
                        reason="kca09b_routing_policy_create",
                        metadata_safe={
                            "product_code": product,
                            "payment_method": payment_method.value,
                            "environment": environment.value,
                            "requires_recurring": requires_recurring,
                            "requires_webhooks": requires_webhooks,
                            "provider_account_count": len(ordered),
                        },
                        instante=instante,
                    )
                )
                return policy
        except IntegrityError as exc:
            raise RegistroComercialDuplicado(
                "billing_routing_scope_duplicate"
            ) from exc

    def atualizar_routing_policy(
        self,
        *,
        contexto: ContextoExecucao,
        routing_policy_id: str,
        expected_version: int,
        primary_provider_account_id: str,
        fallback_provider_account_ids: tuple[str, ...],
        active: bool,
        requires_recurring: bool,
        requires_webhooks: bool,
    ) -> BillingRoutingPolicy:
        policy_id = routing_policy_id.strip()
        primary = primary_provider_account_id.strip()
        fallbacks = tuple(item.strip() for item in fallback_provider_account_ids)
        instante = _now()
        with self._session_factory() as session, session.begin():
            shared = RepositorioComercialSQLAlchemy(session)
            repo = RepositorioBillingConfigSQLAlchemy(session)
            current = repo.obter_routing_policy(policy_id)
            if current is None:
                raise RegistroComercialNaoEncontrado(
                    "billing_routing_policy_not_found"
                )
            if active:
                self._validar_route_accounts(
                    repo=repo,
                    account_ids=(primary, *fallbacks),
                    payment_method=current.payment_method,
                    environment=current.environment,
                    requires_recurring=requires_recurring,
                    requires_webhooks=requires_webhooks,
                )
            updated = repo.atualizar_routing_policy(
                routing_policy_id=policy_id,
                expected_version=expected_version,
                values={
                    "primary_provider_account_id": primary,
                    "fallback_provider_account_ids": list(fallbacks),
                    "requires_recurring": requires_recurring,
                    "requires_webhooks": requires_webhooks,
                    "active": active,
                    "correlation_id": contexto.correlation_id,
                    "updated_by": self._actor(contexto),
                },
            )
            shared.adicionar_auditoria(
                self._audit(
                    contexto=contexto,
                    action="commercial.billing.routing_policy.update",
                    aggregate_type="billing_routing_policy",
                    aggregate_id=policy_id,
                    result="success",
                    reason="kca09b_routing_policy_update",
                    metadata_safe={
                        "product_code": updated.product_code,
                        "payment_method": updated.payment_method.value,
                        "environment": updated.environment.value,
                        "requires_recurring": updated.requires_recurring,
                        "requires_webhooks": updated.requires_webhooks,
                        "active": updated.active,
                        "provider_account_count": 1
                        + len(updated.fallback_provider_account_ids),
                        "version": updated.version,
                    },
                    instante=instante,
                )
            )
            return updated

    def listar_routing_policies(self) -> tuple[BillingRoutingPolicy, ...]:
        with self._session_factory() as session:
            return RepositorioBillingConfigSQLAlchemy(
                session
            ).listar_routing_policies()

    def resolver_rota(
        self,
        *,
        product_code: str,
        payment_method: BillingPaymentMethod,
        environment: BillingEnvironment,
    ) -> BillingRouteDecision:
        product = normalizar_product_code(product_code)
        with self._session_factory() as session:
            repo = RepositorioBillingConfigSQLAlchemy(session)
            policy = repo.obter_routing_policy_scope(
                product_code=product,
                payment_method=payment_method,
                environment=environment,
            )
            if policy is None or not policy.active:
                raise DadoComercialInvalido("billing_route_unavailable")
            ordered_ids = (
                policy.primary_provider_account_id,
                *policy.fallback_provider_account_ids,
            )
            available: list[BillingRouteAccount] = []
            for account_id in ordered_ids:
                account = repo.obter_provider_account(account_id)
                if account is None:
                    continue
                if account.status != BillingProviderAccountStatus.ACTIVE:
                    continue
                if account.environment != environment:
                    continue
                if payment_method not in account.supported_payment_methods:
                    continue
                if policy.requires_recurring and not account.supports_recurring:
                    continue
                if policy.requires_webhooks and not account.supports_webhooks:
                    continue
                available.append(
                    BillingRouteAccount(
                        provider_account_id=account.provider_account_id,
                        provider_code=account.provider_code,
                        priority=account.priority,
                    )
                )
        if not available:
            raise DadoComercialInvalido("billing_route_unavailable")
        return BillingRouteDecision(
            product_code=product,
            payment_method=payment_method,
            environment=environment,
            accounts=tuple(available),
        )
