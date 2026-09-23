"""Superfície comercial autenticada do cliente Kordena — KCA-11."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from application.commercial_access import AplicacaoAcessoComercialV1
from application.commercial_billing import BillingProviderAdapterRegistryV1
from application.commercial_checkout import AplicacaoCheckoutComercialV1
from core.comercial.billing import BillingProviderError
from core.comercial.billing_config import BillingEnvironment, BillingPaymentMethod
from core.comercial.erros import (
    DadoComercialInvalido,
    RegistroComercialNaoEncontrado,
)
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from http_api.auth import AuthSessionRuntime

IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=192),
]


class CommercialCheckoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str = Field(min_length=1, max_length=64)
    plan_version_id: str = Field(min_length=1, max_length=64)
    price_id: str = Field(min_length=1, max_length=64)
    payment_method: BillingPaymentMethod
    success_url: str = Field(min_length=1, max_length=2048)
    cancel_url: str = Field(min_length=1, max_length=2048)


def _return_url(value: str, *, request: Request, production: bool) -> str:
    origin = request.headers.get("origin", "").strip()
    if not origin:
        raise DadoComercialInvalido("checkout_origin_required")
    parsed = urlparse(value)
    origin_parsed = urlparse(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise DadoComercialInvalido("checkout_return_url_invalid")
    if (parsed.scheme, parsed.netloc) != (
        origin_parsed.scheme,
        origin_parsed.netloc,
    ):
        raise DadoComercialInvalido("checkout_return_url_origin_mismatch")
    if production and parsed.scheme != "https":
        raise DadoComercialInvalido("checkout_return_url_https_required")
    return value


def build_commercial_access_router(
    *,
    session_factory,
    auth_runtime: AuthSessionRuntime,
    enforcement_enabled: bool,
    billing_adapter_registry: BillingProviderAdapterRegistryV1 | None = None,
    billing_secret_store: SecretStore | None = None,
    billing_environment: BillingEnvironment = BillingEnvironment.SANDBOX,
) -> APIRouter:
    router = APIRouter(prefix="/v1/commercial", tags=["commercial-account"])
    app = AplicacaoAcessoComercialV1(
        session_factory,
        enforcement_enabled=enforcement_enabled,
    )
    billing_registry = billing_adapter_registry or BillingProviderAdapterRegistryV1()
    billing_store = billing_secret_store or ReferenceSecretStore()
    checkout_app = AplicacaoCheckoutComercialV1(
        session_factory,
        adapter_registry=billing_registry,
        fallback_secret_store=billing_store,
    )

    def _identity(request: Request):
        identity = auth_runtime.resolver_identidade(request)
        if identity is None:
            raise CredenciaisInvalidas("credenciais invalidas")
        return identity

    def _error(exc: Exception) -> JSONResponse:
        if isinstance(exc, ErroSeguranca):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"erro": getattr(exc, "codigo", "credenciais_invalidas")},
            )
        if isinstance(exc, PermissionError):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"erro": str(exc)},
            )
        if isinstance(exc, RegistroComercialNaoEncontrado):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"erro": str(exc)},
            )
        if isinstance(exc, BillingProviderError):
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"erro": type(exc).__name__},
            )
        if isinstance(exc, DadoComercialInvalido):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"erro": str(exc)},
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"erro": "commercial_internal_error"},
        )

    @router.get("/access", response_model=None)
    def access_status(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            identity = _identity(request)
            result = app.avaliar(tenant_id=identity.tenant_id)
            return {
                "tenant_id": result.tenant_id,
                "enforcement_enabled": result.enforcement_enabled,
                "managed": result.managed,
                "product_account_id": result.product_account_id,
                "operational_allowed": result.operational_allowed,
                "entitled": result.entitled,
                "access_mode": (
                    result.access_mode.value if result.access_mode is not None else None
                ),
                "reason": result.reason,
                "revision": result.revision,
                "stale": result.stale,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.get("/plans", response_model=None)
    def plans(request: Request) -> list[dict[str, Any]] | JSONResponse:
        try:
            _identity(request)
            return [
                {
                    "plan_code": item.plan_code,
                    "rank": item.rank,
                    "plan_version_id": item.plan_version_id,
                    "display_name": item.display_name,
                    "description": item.description,
                    "marketing_badge": item.marketing_badge,
                    "prices": [
                        {
                            "price_id": price.price_id,
                            "currency": price.currency,
                            "billing_period": price.billing_period,
                            "amount": str(price.amount),
                        }
                        for price in item.prices
                    ],
                }
                for item in app.listar_ofertas()
            ]
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.get("/subscription", response_model=None)
    def subscription(request: Request) -> dict[str, Any] | JSONResponse:
        try:
            identity = _identity(request)
            current = app.obter_assinatura(tenant_id=identity.tenant_id)
            if current is None:
                return {"subscription": None}
            return {
                "subscription": {
                    "subscription_id": current.subscription_id,
                    "product_account_id": current.product_account_id,
                    "status": current.status.value,
                    "plan_code": current.plan_code,
                    "plan_version_id": current.plan_version_id,
                    "price_id": current.price_id,
                    "currency": current.currency,
                    "billing_period": current.billing_period,
                    "contracted_amount": str(current.contracted_amount),
                    "current_period_start": (
                        current.current_period_start.isoformat()
                        if current.current_period_start
                        else None
                    ),
                    "current_period_end": (
                        current.current_period_end.isoformat()
                        if current.current_period_end
                        else None
                    ),
                    "cancel_at_period_end": current.cancel_at_period_end,
                    "version": current.version,
                }
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    @router.post("/checkout", response_model=None)
    def checkout(
        payload: CommercialCheckoutIn,
        request: Request,
        idempotency_key: IdempotencyHeader,
    ) -> dict[str, Any] | JSONResponse:
        try:
            identity = _identity(request)
            success_url = _return_url(
                payload.success_url,
                request=request,
                production=billing_environment == BillingEnvironment.PRODUCTION,
            )
            cancel_url = _return_url(
                payload.cancel_url,
                request=request,
                production=billing_environment == BillingEnvironment.PRODUCTION,
            )
            result = checkout_app.iniciar(
                contexto=identity.contexto(
                    origem="commercial_customer_checkout_v1",
                    correlation_id=request.headers.get("x-correlation-id"),
                ),
                idempotency_key=idempotency_key,
                tenant_id=identity.tenant_id,
                plan_code=payload.plan_code,
                plan_version_id=payload.plan_version_id,
                price_id=payload.price_id,
                payment_method=payload.payment_method,
                environment=billing_environment,
                success_url=success_url,
                cancel_url=cancel_url,
            )
            return {
                "subscription_id": result.subscription.subscription_id,
                "subscription_status": result.subscription.status.value,
                "provider_code": result.provider_code,
                "provider_account_id": result.provider_account_id,
                "external_checkout_ref": result.external_checkout_ref,
                "billing_binding_id": result.billing_binding_id,
                "checkout_url": result.checkout_url,
            }
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    return router
