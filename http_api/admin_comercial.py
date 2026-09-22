"""Fronteira HTTP administrativa do Commercial Registry KCA-01."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr
from sqlalchemy.orm import Session

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_catalog import AplicacaoCatalogoComercialV1
from application.commercial_billing import BillingProviderAdapterRegistryV1
from application.commercial_billing_config import AplicacaoBillingConfigurationV1
from core.comercial.billing_config import (
    BillingEnvironment,
    BillingPaymentMethod,
    BillingProviderAccountStatus,
)
from core.comercial.catalogo import (
    EntitlementPlano,
    PoliticaMudancaPreco,
    TipoDescontoPromocao,
)
from core.comercial.erros import (
    ConflitoConcorrenciaComercial,
    ConflitoIdempotenciaComercial,
    DadoComercialInvalido,
    RegistroComercialDuplicado,
    RegistroComercialNaoEncontrado,
    TransicaoComercialInvalida,
)
from core.comercial.modelos import (
    ClasseContaComercial,
    ClienteComercial,
    ContaProdutoComercial,
    StatusClienteComercial,
    StatusContaProduto,
)
from http_api.admin_backoffice import contexto_backoffice
from http_api.admin_dashboard import _tratar_erro
from http_api.auth import AuthSessionRuntime
from core.seguranca.segredos import ReferenceSecretStore, SecretStore

SessionFactory = Callable[[], Session]
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=192),
]


class CustomerCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    account_class: ClasseContaComercial
    primary_contact_email: EmailStr
    primary_contact_phone: str | None = Field(default=None, max_length=64)


class CustomerUpdateIn(CustomerCreateIn):
    expected_version: int = Field(ge=1)
    status: StatusClienteComercial


class ProductAccountCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_code: str = Field(min_length=1, max_length=64)
    product_tenant_id: str | None = Field(default=None, max_length=64)


class ProductAccountTransitionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: StatusContaProduto
    product_tenant_id: str | None = Field(default=None, max_length=64)


class EntitlementPlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_key: str = Field(min_length=1, max_length=128)
    enabled: bool
    limit_value: Decimal | None = Field(default=None, ge=0)
    limit_unit: str | None = Field(default=None, max_length=32)
    config: dict[str, Any] = Field(default_factory=dict)


class PlanVersionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1000)
    trial_eligible: bool = True
    marketing_badge: str | None = Field(default=None, max_length=96)
    metadata: dict[str, Any] = Field(default_factory=dict)
    entitlements: list[EntitlementPlanIn] = Field(default_factory=list)
    change_reason: str = Field(min_length=1, max_length=255)


class CatalogValidateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    change_reason: str = Field(min_length=1, max_length=255)


class PlanVersionPublishIn(CatalogValidateIn):
    expected_plan_version: int = Field(ge=1)
    effective_from: datetime


class PriceCreateIn(CatalogValidateIn):
    currency: str = Field(min_length=3, max_length=3)
    billing_period: str = Field(min_length=1, max_length=32)
    amount: Decimal = Field(ge=0)
    change_policy: PoliticaMudancaPreco


class PricePublishIn(CatalogValidateIn):
    expected_plan_version: int = Field(ge=1)
    effective_from: datetime


class PromotionVersionBaseIn(CatalogValidateIn):
    name: str = Field(min_length=1, max_length=128)
    discount_type: TipoDescontoPromocao
    discount_value: Decimal = Field(gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    starts_at: datetime
    ends_at: datetime | None = None
    eligible_plan_codes: list[str] = Field(min_length=1)
    max_redemptions: int | None = Field(default=None, ge=1)
    per_customer_limit: int | None = Field(default=None, ge=1)
    rules: dict[str, Any] = Field(default_factory=dict)


class PromotionPublishIn(CatalogValidateIn):
    expected_promotion_version: int = Field(ge=1)


class BillingProviderAccountCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_code: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    legal_entity_ref: str | None = Field(default=None, max_length=128)
    environment: BillingEnvironment
    credential_secret_reference: str | None = Field(
        default=None, min_length=3, max_length=255
    )
    supported_payment_methods: list[BillingPaymentMethod] = Field(min_length=1)
    supports_recurring: bool = False
    supports_webhooks: bool = False
    priority: int = Field(default=100, ge=0, le=100000)


class BillingProviderAccountUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    display_name: str = Field(min_length=1, max_length=128)
    legal_entity_ref: str | None = Field(default=None, max_length=128)
    credential_secret_reference: str | None = Field(
        default=None, min_length=3, max_length=255
    )
    supported_payment_methods: list[BillingPaymentMethod] = Field(min_length=1)
    supports_recurring: bool = False
    supports_webhooks: bool = False
    priority: int = Field(default=100, ge=0, le=100000)


class BillingProviderCredentialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    credential: SecretStr


class BillingProviderConnectionTestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    timeout_seconds: float = Field(default=10.0, gt=0, le=120)


class BillingProviderStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    status: BillingProviderAccountStatus


class BillingRoutingPolicyCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_code: str = Field(min_length=1, max_length=64)
    payment_method: BillingPaymentMethod
    environment: BillingEnvironment
    requires_recurring: bool = False
    requires_webhooks: bool = False
    primary_provider_account_id: str = Field(min_length=1, max_length=64)
    fallback_provider_account_ids: list[str] = Field(default_factory=list)


class BillingRoutingPolicyUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    primary_provider_account_id: str = Field(min_length=1, max_length=64)
    fallback_provider_account_ids: list[str] = Field(default_factory=list)
    active: bool = True
    requires_recurring: bool = False
    requires_webhooks: bool = False


def _catalog_out(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _catalog_out(asdict(value))  # type: ignore[arg-type]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _catalog_out(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_catalog_out(item) for item in value]
    return value


def _billing_provider_out(account: Any) -> dict[str, Any]:
    return {
        "provider_account_id": account.provider_account_id,
        "provider_code": account.provider_code,
        "display_name": account.display_name,
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
        "last_tested_at": (
            account.last_tested_at.isoformat() if account.last_tested_at else None
        ),
        "last_test_status": account.last_test_status.value,
        "version": account.version,
        "updated_at": account.updated_at.isoformat(),
    }


def _billing_routing_out(policy: Any) -> dict[str, Any]:
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


def _customer_out(customer: ClienteComercial) -> dict[str, Any]:
    return {
        "fm_customer_id": customer.fm_customer_id,
        "customer_code": customer.customer_code,
        "display_name": customer.display_name,
        "legal_name": customer.legal_name,
        "status": customer.status.value,
        "account_class": customer.account_class.value,
        "primary_contact_email": customer.primary_contact_email,
        "primary_contact_phone": customer.primary_contact_phone,
        "version": customer.version,
        "created_at": customer.created_at.isoformat(),
        "updated_at": customer.updated_at.isoformat(),
    }


def _product_account_out(account: ContaProdutoComercial) -> dict[str, Any]:
    return {
        "product_account_id": account.product_account_id,
        "fm_customer_id": account.fm_customer_id,
        "product_code": account.product_code,
        "product_tenant_id": account.product_tenant_id,
        "status": account.status.value,
        "version": account.version,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
        "activated_at": (
            account.activated_at.isoformat() if account.activated_at else None
        ),
        "suspended_at": (
            account.suspended_at.isoformat() if account.suspended_at else None
        ),
        "closed_at": account.closed_at.isoformat() if account.closed_at else None,
    }


def _erro_comercial(exc: Exception) -> JSONResponse:
    if isinstance(exc, RegistroComercialNaoEncontrado):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"erro": str(exc)},
        )
    if isinstance(
        exc,
        (
            ConflitoConcorrenciaComercial,
            ConflitoIdempotenciaComercial,
            RegistroComercialDuplicado,
        ),
    ):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"erro": str(exc)},
        )
    if isinstance(exc, (DadoComercialInvalido, TransicaoComercialInvalida)):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(exc)},
        )
    return _tratar_erro(exc)


def build_admin_comercial_router(
    *,
    session_factory: SessionFactory,
    auth_runtime: AuthSessionRuntime,
    billing_adapter_registry: BillingProviderAdapterRegistryV1 | None = None,
    billing_secret_store: SecretStore | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/admin/commercial", tags=["admin-commercial"])
    app = AplicacaoCommercialRegistryV1(session_factory)
    catalog_app = AplicacaoCatalogoComercialV1(session_factory)
    billing_app = AplicacaoBillingConfigurationV1(
        session_factory,
        adapter_registry=(
            billing_adapter_registry or BillingProviderAdapterRegistryV1()
        ),
        secret_store=billing_secret_store or ReferenceSecretStore(),
    )

    def contexto(request: Request):
        return contexto_backoffice(
            request,
            auth_runtime=auth_runtime,
            origem="admin_commercial_http_v1",
        )

    @router.post("/customers", status_code=201, response_model=None)
    def criar_customer(
        payload: CustomerCreateIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            customer = app.criar_cliente(
                contexto=contexto(request),
                idempotency_key=idempotency_key,
                display_name=payload.display_name,
                legal_name=payload.legal_name,
                account_class=payload.account_class,
                primary_contact_email=str(payload.primary_contact_email),
                primary_contact_phone=payload.primary_contact_phone,
            )
            return _customer_out(customer)
        except Exception as exc:  # noqa: BLE001 - boundary HTTP fail-closed
            return _erro_comercial(exc)

    @router.get("/customers/{fm_customer_id}", response_model=None)
    def obter_customer(
        fm_customer_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto(request)
            return _customer_out(app.obter_cliente(fm_customer_id=fm_customer_id))
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.put("/customers/{fm_customer_id}", response_model=None)
    def atualizar_customer(
        fm_customer_id: str,
        payload: CustomerUpdateIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            customer = app.atualizar_cliente(
                contexto=contexto(request),
                fm_customer_id=fm_customer_id,
                expected_version=payload.expected_version,
                display_name=payload.display_name,
                legal_name=payload.legal_name,
                status=payload.status,
                account_class=payload.account_class,
                primary_contact_email=str(payload.primary_contact_email),
                primary_contact_phone=payload.primary_contact_phone,
            )
            return _customer_out(customer)
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/customers/{fm_customer_id}/product-accounts",
        status_code=201,
        response_model=None,
    )
    def criar_product_account(
        fm_customer_id: str,
        payload: ProductAccountCreateIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            account = app.criar_conta_produto(
                contexto=contexto(request),
                idempotency_key=idempotency_key,
                fm_customer_id=fm_customer_id,
                product_code=payload.product_code,
                product_tenant_id=payload.product_tenant_id,
            )
            return _product_account_out(account)
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/product-accounts/{product_account_id}", response_model=None)
    def obter_product_account(
        product_account_id: str,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            contexto(request)
            return _product_account_out(
                app.obter_conta_produto(product_account_id=product_account_id)
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/product-accounts/{product_account_id}/transition",
        response_model=None,
    )
    def transicionar_product_account(
        product_account_id: str,
        payload: ProductAccountTransitionIn,
        request: Request,
    ) -> dict[str, Any] | JSONResponse:
        try:
            account = app.transicionar_conta_produto(
                contexto=contexto(request),
                product_account_id=product_account_id,
                expected_version=payload.expected_version,
                status=payload.status,
                product_tenant_id=payload.product_tenant_id,
            )
            return _product_account_out(account)
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/catalog/kordena", response_model=None)
    def listar_catalogo(request: Request) -> Any:
        try:
            return _catalog_out(
                catalog_app.listar_catalogo_kordena(contexto=contexto(request))
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post("/plans/{plan_code}/versions", status_code=201, response_model=None)
    def criar_plan_version(
        plan_code: str,
        payload: PlanVersionCreateIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            entitlements = tuple(
                EntitlementPlano(
                    capability_key=item.capability_key,
                    enabled=item.enabled,
                    limit_value=item.limit_value,
                    limit_unit=item.limit_unit,
                    config=item.config,
                )
                for item in payload.entitlements
            )
            return _catalog_out(
                catalog_app.criar_versao_plano(
                    contexto=contexto(request),
                    idempotency_key=idempotency_key,
                    plan_code=plan_code,
                    display_name=payload.display_name,
                    description=payload.description,
                    trial_eligible=payload.trial_eligible,
                    marketing_badge=payload.marketing_badge,
                    metadata=payload.metadata,
                    entitlements=entitlements,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post("/plan-versions/{plan_version_id}/validate", response_model=None)
    def validar_plan_version(
        plan_version_id: str,
        payload: CatalogValidateIn,
        request: Request,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.validar_versao_plano(
                    contexto=contexto(request),
                    plan_version_id=plan_version_id,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/plan-versions/{plan_version_id}/preview", response_model=None)
    def preview_plan_version(plan_version_id: str, request: Request) -> Any:
        try:
            return _catalog_out(
                catalog_app.preview_versao_plano(
                    contexto=contexto(request),
                    plan_version_id=plan_version_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post("/plan-versions/{plan_version_id}/publish", response_model=None)
    def publicar_plan_version(
        plan_version_id: str,
        payload: PlanVersionPublishIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.publicar_versao_plano(
                    contexto=contexto(request),
                    idempotency_key=idempotency_key,
                    plan_version_id=plan_version_id,
                    expected_plan_version=payload.expected_plan_version,
                    effective_from=payload.effective_from,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post("/plan-versions/{plan_version_id}/prices", status_code=201, response_model=None)
    def criar_price(
        plan_version_id: str,
        payload: PriceCreateIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.criar_preco(
                    contexto=contexto(request),
                    idempotency_key=idempotency_key,
                    plan_version_id=plan_version_id,
                    currency=payload.currency,
                    billing_period=payload.billing_period,
                    amount=payload.amount,
                    change_policy=payload.change_policy,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post("/prices/{price_id}/validate", response_model=None)
    def validar_price(
        price_id: str,
        payload: CatalogValidateIn,
        request: Request,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.validar_preco(
                    contexto=contexto(request),
                    price_id=price_id,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/prices/{price_id}/preview", response_model=None)
    def preview_price(price_id: str, request: Request) -> Any:
        try:
            return _catalog_out(
                catalog_app.preview_preco(
                    contexto=contexto(request),
                    price_id=price_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post("/prices/{price_id}/publish", response_model=None)
    def publicar_price(
        price_id: str,
        payload: PricePublishIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.publicar_preco(
                    contexto=contexto(request),
                    idempotency_key=idempotency_key,
                    price_id=price_id,
                    expected_plan_version=payload.expected_plan_version,
                    effective_from=payload.effective_from,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/promotions", response_model=None)
    def listar_promotions(request: Request) -> Any:
        try:
            return _catalog_out(
                catalog_app.listar_promocoes(contexto=contexto(request))
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post("/promotions", status_code=201, response_model=None)
    def criar_promotion(
        payload: PromotionVersionBaseIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            promotion, version = catalog_app.criar_promocao(
                contexto=contexto(request),
                idempotency_key=idempotency_key,
                name=payload.name,
                discount_type=payload.discount_type,
                discount_value=payload.discount_value,
                currency=payload.currency,
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
                eligible_plan_codes=tuple(payload.eligible_plan_codes),
                max_redemptions=payload.max_redemptions,
                per_customer_limit=payload.per_customer_limit,
                rules=payload.rules,
                change_reason=payload.change_reason,
            )
            return _catalog_out({"promotion": promotion, "version": version})
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/promotions/{promotion_id}/versions",
        status_code=201,
        response_model=None,
    )
    def criar_promotion_version(
        promotion_id: str,
        payload: PromotionVersionBaseIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.criar_versao_promocao(
                    contexto=contexto(request),
                    idempotency_key=idempotency_key,
                    promotion_id=promotion_id,
                    name=payload.name,
                    discount_type=payload.discount_type,
                    discount_value=payload.discount_value,
                    currency=payload.currency,
                    starts_at=payload.starts_at,
                    ends_at=payload.ends_at,
                    eligible_plan_codes=tuple(payload.eligible_plan_codes),
                    max_redemptions=payload.max_redemptions,
                    per_customer_limit=payload.per_customer_limit,
                    rules=payload.rules,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/promotion-versions/{promotion_version_id}/validate",
        response_model=None,
    )
    def validar_promotion_version(
        promotion_version_id: str,
        payload: CatalogValidateIn,
        request: Request,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.validar_versao_promocao(
                    contexto=contexto(request),
                    promotion_version_id=promotion_version_id,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get(
        "/promotion-versions/{promotion_version_id}/preview",
        response_model=None,
    )
    def preview_promotion_version(
        promotion_version_id: str,
        request: Request,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.preview_promocao(
                    contexto=contexto(request),
                    promotion_version_id=promotion_version_id,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/promotion-versions/{promotion_version_id}/publish",
        response_model=None,
    )
    def publicar_promotion_version(
        promotion_version_id: str,
        payload: PromotionPublishIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            return _catalog_out(
                catalog_app.publicar_versao_promocao(
                    contexto=contexto(request),
                    idempotency_key=idempotency_key,
                    promotion_version_id=promotion_version_id,
                    expected_promotion_version=payload.expected_promotion_version,
                    change_reason=payload.change_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/billing/provider-accounts",
        status_code=201,
        response_model=None,
    )
    def criar_billing_provider_account(
        payload: BillingProviderAccountCreateIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            account = billing_app.criar_provider_account(
                contexto=contexto(request),
                idempotency_key=idempotency_key,
                provider_code=payload.provider_code,
                display_name=payload.display_name,
                legal_entity_ref=payload.legal_entity_ref,
                environment=payload.environment,
                credential_secret_reference=payload.credential_secret_reference,
                supported_payment_methods=tuple(payload.supported_payment_methods),
                supports_recurring=payload.supports_recurring,
                supports_webhooks=payload.supports_webhooks,
                priority=payload.priority,
            )
            return _billing_provider_out(account)
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/billing/provider-accounts", response_model=None)
    def listar_billing_provider_accounts(request: Request) -> Any:
        try:
            contexto(request)
            return [
                _billing_provider_out(item)
                for item in billing_app.listar_provider_accounts()
            ]
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.put(
        "/billing/provider-accounts/{provider_account_id}",
        response_model=None,
    )
    def atualizar_billing_provider_account(
        provider_account_id: str,
        payload: BillingProviderAccountUpdateIn,
        request: Request,
    ) -> Any:
        try:
            return _billing_provider_out(
                billing_app.atualizar_provider_account(
                    contexto=contexto(request),
                    provider_account_id=provider_account_id,
                    expected_version=payload.expected_version,
                    display_name=payload.display_name,
                    legal_entity_ref=payload.legal_entity_ref,
                    credential_secret_reference=payload.credential_secret_reference,
                    supported_payment_methods=tuple(
                        payload.supported_payment_methods
                    ),
                    supports_recurring=payload.supports_recurring,
                    supports_webhooks=payload.supports_webhooks,
                    priority=payload.priority,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/billing/provider-accounts/{provider_account_id}/credential",
        response_model=None,
    )
    def armazenar_billing_provider_credential(
        provider_account_id: str,
        payload: BillingProviderCredentialIn,
        request: Request,
    ) -> Any:
        try:
            return _billing_provider_out(
                billing_app.armazenar_credencial(
                    contexto=contexto(request),
                    provider_account_id=provider_account_id,
                    expected_version=payload.expected_version,
                    credential_value=payload.credential.get_secret_value(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/billing/provider-accounts/{provider_account_id}/test-connection",
        response_model=None,
    )
    def testar_billing_provider_account(
        provider_account_id: str,
        payload: BillingProviderConnectionTestIn,
        request: Request,
    ) -> Any:
        try:
            result = billing_app.testar_conexao(
                contexto=contexto(request),
                provider_account_id=provider_account_id,
                expected_version=payload.expected_version,
                timeout_seconds=payload.timeout_seconds,
            )
            return {
                "ok": result.ok,
                "detail_code": result.detail_code,
                "account": _billing_provider_out(result.account),
            }
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/billing/provider-accounts/{provider_account_id}/status",
        response_model=None,
    )
    def transicionar_billing_provider_account(
        provider_account_id: str,
        payload: BillingProviderStatusIn,
        request: Request,
    ) -> Any:
        try:
            return _billing_provider_out(
                billing_app.transicionar_provider_account(
                    contexto=contexto(request),
                    provider_account_id=provider_account_id,
                    expected_version=payload.expected_version,
                    status=payload.status,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.post(
        "/billing/routing-policies",
        status_code=201,
        response_model=None,
    )
    def criar_billing_routing_policy(
        payload: BillingRoutingPolicyCreateIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> Any:
        try:
            return _billing_routing_out(
                billing_app.criar_routing_policy(
                    contexto=contexto(request),
                    idempotency_key=idempotency_key,
                    product_code=payload.product_code,
                    payment_method=payload.payment_method,
                    environment=payload.environment,
                    primary_provider_account_id=(
                        payload.primary_provider_account_id
                    ),
                    fallback_provider_account_ids=tuple(
                        payload.fallback_provider_account_ids
                    ),
                    requires_recurring=payload.requires_recurring,
                    requires_webhooks=payload.requires_webhooks,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/billing/routing-policies", response_model=None)
    def listar_billing_routing_policies(request: Request) -> Any:
        try:
            contexto(request)
            return [
                _billing_routing_out(item)
                for item in billing_app.listar_routing_policies()
            ]
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.put(
        "/billing/routing-policies/{routing_policy_id}",
        response_model=None,
    )
    def atualizar_billing_routing_policy(
        routing_policy_id: str,
        payload: BillingRoutingPolicyUpdateIn,
        request: Request,
    ) -> Any:
        try:
            return _billing_routing_out(
                billing_app.atualizar_routing_policy(
                    contexto=contexto(request),
                    routing_policy_id=routing_policy_id,
                    expected_version=payload.expected_version,
                    primary_provider_account_id=(
                        payload.primary_provider_account_id
                    ),
                    fallback_provider_account_ids=tuple(
                        payload.fallback_provider_account_ids
                    ),
                    active=payload.active,
                    requires_recurring=payload.requires_recurring,
                    requires_webhooks=payload.requires_webhooks,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    @router.get("/billing/route-preview", response_model=None)
    def preview_billing_route(
        product_code: str,
        payment_method: BillingPaymentMethod,
        environment: BillingEnvironment,
        request: Request,
    ) -> Any:
        try:
            contexto(request)
            decision = billing_app.resolver_rota(
                product_code=product_code,
                payment_method=payment_method,
                environment=environment,
            )
            return {
                "product_code": decision.product_code,
                "payment_method": decision.payment_method.value,
                "environment": decision.environment.value,
                "accounts": [
                    {
                        "provider_account_id": item.provider_account_id,
                        "provider_code": item.provider_code,
                        "priority": item.priority,
                    }
                    for item in decision.accounts
                ],
            }
        except Exception as exc:  # noqa: BLE001
            return _erro_comercial(exc)

    return router
