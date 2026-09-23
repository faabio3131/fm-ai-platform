"""Superfície comercial autenticada do cliente Kordena — KCA-11."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from application.commercial_access import AplicacaoAcessoComercialV1
from core.seguranca.erros import CredenciaisInvalidas, ErroSeguranca
from http_api.auth import AuthSessionRuntime


def build_commercial_access_router(
    *,
    session_factory,
    auth_runtime: AuthSessionRuntime,
    enforcement_enabled: bool,
) -> APIRouter:
    router = APIRouter(prefix="/v1/commercial", tags=["commercial-account"])
    app = AplicacaoAcessoComercialV1(
        session_factory,
        enforcement_enabled=enforcement_enabled,
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
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"erro": str(exc)},
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

    return router
