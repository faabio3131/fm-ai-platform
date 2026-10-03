"""Command/FM control plane for Nova FM SaaS billing configuration.

The tenant payment gateway remains outside this surface. This boundary manages
only platform-owned receivables/billing provider accounts used to collect SaaS
license revenue for Nova FM products.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from application.commercial_billing import BillingProviderAdapterRegistryV1
from application.commercial_billing_config import AplicacaoBillingConfigurationV1
from core.comercial.billing_config import (
    BillingEnvironment,
    BillingLegalEntityType,
    BillingPaymentMethod,
    BillingProviderAccountStatus,
)
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretStore
from http_api.fmcc_commercial_control import (
    FMCCActorIn,
    _authorize,
    _commercial_error,
    _context,
    _fresh_step_up,
)


class FMCCBillingProviderCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    provider_code: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    legal_entity_type: BillingLegalEntityType | None = None
    legal_entity_ref: str | None = Field(default=None, max_length=128)
    environment: BillingEnvironment
    supported_payment_methods: list[BillingPaymentMethod] = Field(min_length=1)
    supports_recurring: bool = False
    supports_webhooks: bool = False
    priority: int = Field(default=100, ge=0, le=100000)


class FMCCBillingProviderUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    expected_version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=128)
    legal_entity_type: BillingLegalEntityType | None = None
    legal_entity_ref: str | None = Field(default=None, max_length=128)
    supported_payment_methods: list[BillingPaymentMethod] = Field(min_length=1)
    supports_recurring: bool = False
    supports_webhooks: bool = False
    priority: int = Field(default=100, ge=0, le=100000)


class FMCCBillingCredentialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    expected_version: int = Field(ge=1)
    credential: SecretStr


class FMCCBillingConnectionTestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    expected_version: int = Field(ge=1)
    timeout_seconds: float = Field(default=10.0, gt=0, le=120)


class FMCCBillingProviderStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    expected_version: int = Field(ge=1)
    status: BillingProviderAccountStatus


class FMCCBillingRoutingCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    product_code: str = Field(min_length=1, max_length=64)
    payment_method: BillingPaymentMethod
    environment: BillingEnvironment
    requires_recurring: bool = False
    requires_webhooks: bool = False
    primary_provider_account_id: str = Field(min_length=1, max_length=64)
    fallback_provider_account_ids: list[str] = Field(default_factory=list)


class FMCCBillingRoutingUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: FMCCActorIn
    expected_version: int = Field(ge=1)
    primary_provider_account_id: str = Field(min_length=1, max_length=64)
    fallback_provider_account_ids: list[str] = Field(default_factory=list)
    active: bool = True
    requires_recurring: bool = False
    requires_webhooks: bool = False


def _provider_out(account: Any) -> dict[str, Any]:
    return {
        "provider_account_id": account.provider_account_id,
        "provider_code": account.provider_code,
        "display_name": account.display_name,
        "legal_entity_type": (
            account.legal_entity_type.value
            if account.legal_entity_type is not None
            else None
        ),
        "legal_entity_ref": account.legal_entity_ref,
        "environment": account.environment.value,
        "status": account.status.value,
        "credential_configured": bool(account.credential_secret_reference),
        "supported_payment_methods": [
            item.value for item in account.supported_payment_methods
        ],
        "supports_recurring": account.supports_recurring,
        "supports_webhooks": account.supports_webhooks,
        "priority": account.priority,
        "last_test_status": account.last_test_status.value,
        "last_tested_at": (
            account.last_tested_at.isoformat()
            if account.last_tested_at is not None
            else None
        ),
        "version": account.version,
        "updated_at": account.updated_at.isoformat(),
    }


def _routing_out(policy: Any) -> dict[str, Any]:
    return {
        "routing_policy_id": policy.routing_policy_id,
        "product_code": policy.product_code,
        "payment_method": policy.payment_method.value,
        "environment": policy.environment.value,
        "requires_recurring": policy.requires_recurring,
        "requires_webhooks": policy.requires_webhooks,
        "primary_provider_account_id": policy.primary_provider_account_id,
        "fallback_provider_account_ids": list(policy.fallback_provider_account_ids),
        "active": policy.active,
        "version": policy.version,
        "updated_at": policy.updated_at.isoformat(),
    }


def _correlation_id(request: Request, now: datetime) -> str:
    value = request.headers.get("x-correlation-id", "").strip()
    if value:
        return value[:128]
    value = request.headers.get("x-request-id", "").strip()
    if value:
        return value[:128]
    return f"fmcc-billing-{int(now.timestamp() * 1000000)}"


def _mutation_context(
    *,
    actor: FMCCActorIn,
    request: Request,
) -> tuple[Any, JSONResponse | None]:
    now = datetime.now(timezone.utc)
    contexto = _context(
        actor=actor,
        correlation_id=_correlation_id(request, now),
        requested_at=now,
    )
    contexto = replace(
        contexto,
        permissoes=contexto.permissoes
        | frozenset({Permissao.INTEGRACAO_GERENCIAR}),
    )
    if not _fresh_step_up(actor, now=now):
        return (
            contexto,
            JSONResponse(
                status_code=403,
                content={"error": "fmcc_control_plane.step_up_required"},
            ),
        )
    return contexto, None


def build_fmcc_billing_control_router(
    *,
    session_factory,
    control_plane_token: str | None,
    adapter_registry: BillingProviderAdapterRegistryV1,
    secret_store: SecretStore,
) -> APIRouter:
    """Expose billing configuration to the private Command control plane."""

    router = APIRouter(
        prefix="/v1/control-plane/fmcc/billing",
        tags=["fmcc-billing-control-plane"],
    )
    billing = AplicacaoBillingConfigurationV1(
        session_factory,
        adapter_registry=adapter_registry,
        secret_store=secret_store,
    )

    def auth(authorization: str | None) -> JSONResponse | None:
        return _authorize(authorization, control_plane_token)

    @router.get("/configuration-options", response_model=None)
    def configuration_options(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        provider_codes = list(adapter_registry.available_provider_codes())
        return {
            "provider_codes": provider_codes,
            "provider_options": [
                {
                    "provider_code": code,
                    "credential_fields": list(
                        getattr(
                            adapter_registry.resolve(code),
                            "credential_schema",
                            (),
                        )
                    ),
                }
                for code in provider_codes
            ],
            "legal_entity_types": [
                {
                    "value": BillingLegalEntityType.INDIVIDUAL.value,
                    "label": "Pessoa Física",
                },
                {
                    "value": BillingLegalEntityType.COMPANY.value,
                    "label": "Pessoa Jurídica",
                },
            ],
            "payment_methods": [
                item.value for item in BillingPaymentMethod
            ],
            "environments": [
                item.value for item in BillingEnvironment
            ],
        }

    @router.get("/provider-accounts", response_model=None)
    def list_provider_accounts(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> list[dict[str, Any]] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        return [_provider_out(item) for item in billing.listar_provider_accounts()]

    @router.post("/provider-accounts", status_code=201, response_model=None)
    def create_provider_account(
        body: FMCCBillingProviderCreateIn,
        request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _mutation_context(
            actor=body.actor,
            request=request,
        )
        if actor_denied is not None:
            return actor_denied
        try:
            account = billing.criar_provider_account(
                contexto=contexto,
                idempotency_key=idempotency_key,
                provider_code=body.provider_code,
                display_name=body.display_name,
                legal_entity_type=body.legal_entity_type,
                legal_entity_ref=body.legal_entity_ref,
                environment=body.environment,
                credential_secret_reference=None,
                supported_payment_methods=tuple(body.supported_payment_methods),
                supports_recurring=body.supports_recurring,
                supports_webhooks=body.supports_webhooks,
                priority=body.priority,
            )
            return _provider_out(account)
        except Exception as exc:  # noqa: BLE001
            return _commercial_error(exc)

    @router.put("/provider-accounts/{provider_account_id}", response_model=None)
    def update_provider_account(
        provider_account_id: str,
        body: FMCCBillingProviderUpdateIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _mutation_context(
            actor=body.actor,
            request=request,
        )
        if actor_denied is not None:
            return actor_denied
        try:
            account = billing.atualizar_provider_account(
                contexto=contexto,
                provider_account_id=provider_account_id,
                expected_version=body.expected_version,
                display_name=body.display_name,
                legal_entity_type=body.legal_entity_type,
                legal_entity_ref=body.legal_entity_ref,
                credential_secret_reference=None,
                supported_payment_methods=tuple(body.supported_payment_methods),
                supports_recurring=body.supports_recurring,
                supports_webhooks=body.supports_webhooks,
                priority=body.priority,
            )
            return _provider_out(account)
        except Exception as exc:  # noqa: BLE001
            return _commercial_error(exc)

    @router.post(
        "/provider-accounts/{provider_account_id}/credential",
        response_model=None,
    )
    def store_provider_credential(
        provider_account_id: str,
        body: FMCCBillingCredentialIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _mutation_context(
            actor=body.actor,
            request=request,
        )
        if actor_denied is not None:
            return actor_denied
        try:
            account = billing.armazenar_credencial(
                contexto=contexto,
                provider_account_id=provider_account_id,
                expected_version=body.expected_version,
                credential_value=body.credential.get_secret_value(),
            )
            return _provider_out(account)
        except Exception as exc:  # noqa: BLE001
            return _commercial_error(exc)

    @router.post(
        "/provider-accounts/{provider_account_id}/test-connection",
        response_model=None,
    )
    def test_provider_connection(
        provider_account_id: str,
        body: FMCCBillingConnectionTestIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _mutation_context(
            actor=body.actor,
            request=request,
        )
        if actor_denied is not None:
            return actor_denied
        try:
            result = billing.testar_conexao(
                contexto=contexto,
                provider_account_id=provider_account_id,
                expected_version=body.expected_version,
                timeout_seconds=body.timeout_seconds,
            )
            return {
                "ok": result.ok,
                "detail_code": result.detail_code,
                "account": _provider_out(result.account),
            }
        except Exception as exc:  # noqa: BLE001
            return _commercial_error(exc)

    @router.post(
        "/provider-accounts/{provider_account_id}/status",
        response_model=None,
    )
    def transition_provider_status(
        provider_account_id: str,
        body: FMCCBillingProviderStatusIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _mutation_context(
            actor=body.actor,
            request=request,
        )
        if actor_denied is not None:
            return actor_denied
        try:
            account = billing.transicionar_provider_account(
                contexto=contexto,
                provider_account_id=provider_account_id,
                expected_version=body.expected_version,
                status=body.status,
            )
            return _provider_out(account)
        except Exception as exc:  # noqa: BLE001
            return _commercial_error(exc)

    @router.get("/routing-policies", response_model=None)
    def list_routing_policies(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> list[dict[str, Any]] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        return [_routing_out(item) for item in billing.listar_routing_policies()]

    @router.post("/routing-policies", status_code=201, response_model=None)
    def create_routing_policy(
        body: FMCCBillingRoutingCreateIn,
        request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _mutation_context(
            actor=body.actor,
            request=request,
        )
        if actor_denied is not None:
            return actor_denied
        try:
            policy = billing.criar_routing_policy(
                contexto=contexto,
                idempotency_key=idempotency_key,
                product_code=body.product_code,
                payment_method=body.payment_method,
                environment=body.environment,
                primary_provider_account_id=body.primary_provider_account_id,
                fallback_provider_account_ids=tuple(
                    body.fallback_provider_account_ids
                ),
                requires_recurring=body.requires_recurring,
                requires_webhooks=body.requires_webhooks,
            )
            return _routing_out(policy)
        except Exception as exc:  # noqa: BLE001
            return _commercial_error(exc)

    @router.put("/routing-policies/{routing_policy_id}", response_model=None)
    def update_routing_policy(
        routing_policy_id: str,
        body: FMCCBillingRoutingUpdateIn,
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> dict[str, Any] | JSONResponse:
        denied = auth(authorization)
        if denied is not None:
            return denied
        contexto, actor_denied = _mutation_context(
            actor=body.actor,
            request=request,
        )
        if actor_denied is not None:
            return actor_denied
        try:
            policy = billing.atualizar_routing_policy(
                contexto=contexto,
                routing_policy_id=routing_policy_id,
                expected_version=body.expected_version,
                primary_provider_account_id=body.primary_provider_account_id,
                fallback_provider_account_ids=tuple(
                    body.fallback_provider_account_ids
                ),
                active=body.active,
                requires_recurring=body.requires_recurring,
                requires_webhooks=body.requires_webhooks,
            )
            return _routing_out(policy)
        except Exception as exc:  # noqa: BLE001
            return _commercial_error(exc)

    return router
