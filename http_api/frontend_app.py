"""FastAPI factory para o frontend enterprise desacoplado da V1.

Mantém o ``build_http_app`` como autoridade das rotas já promovidas e adiciona
as fronteiras WEB-PARITY em certificação usando exatamente o mesmo engine,
session factory, secret store e runtime de sessão autenticada. A política CORS
local continua restrita a desenvolvimento/teste; ambientes comerciais permanecem
fail-closed para origens localhost.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from application.commercial_access import AplicacaoAcessoComercialV1
from application.commercial_billing import BillingProviderAdapterRegistryV1
from core.comercial.billing_config import BillingEnvironment
from core.runtime import build_engine, load_runtime_settings
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.erros import ErroSeguranca
from core.seguranca.segredos import ReferenceSecretStore
from http_api.admin_assistente_atendimento import (
    build_admin_assistente_atendimento_router,
)
from http_api.admin_auditoria import build_admin_auditoria_router
from http_api.admin_backoffice import build_admin_backoffice_router
from http_api.admin_comercial import build_admin_comercial_router
from http_api.admin_configuracao import build_admin_configuracao_router
from http_api.admin_dashboard import build_admin_dashboard_router
from http_api.admin_empresa import build_admin_empresa_router
from http_api.admin_fiscal import build_admin_fiscal_router
from http_api.admin_impressao import build_admin_impressao_router
from http_api.admin_integracoes import build_admin_integracoes_router
from http_api.admin_notificacoes import build_admin_notificacoes_router
from http_api.admin_usuarios import build_admin_usuarios_router
from http_api.ai_finops import build_ai_finops_router
from http_api.app import build_http_app
from http_api.auth import AuthSessionRuntime
from http_api.cardapio_publico import build_cardapio_publico_router
from http_api.central_pedidos import build_central_pedidos_router
from http_api.commercial_access import build_commercial_access_router
from http_api.fmcc_commercial_control import build_fmcc_commercial_control_router
from http_api.crm import build_crm_router
from http_api.delivery import build_delivery_router
from http_api.entrega import build_entrega_router
from http_api.garcom_web import build_garcom_web_router
from http_api.gerente_ia_web import build_gerente_ia_web_router
from http_api.marketplaces_web import build_marketplaces_web_router
from http_api.operational_auth import obter_identidade_operacional
from http_api.pagamentos_web import build_pagamentos_web_router
from http_api.public_signup import VerificationDispatcher, build_public_signup_router
from infra.seguranca.session_guard import build_session_factory

DEV_FRONTEND_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

FRONTEND_CORS_HEADERS: tuple[str, ...] = (
    "Authorization",
    "Content-Type",
    "X-Tenant-ID",
    "X-Unit-ID",
    "Idempotency-Key",
    "X-Correlation-ID",
)

FRONTEND_CORS_METHODS: tuple[str, ...] = (
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
)


def _configure_frontend_cors(
    app: FastAPI,
    *,
    settings: RuntimeSettings,
) -> FastAPI:
    """Adiciona CORS local somente fora de staging/production."""

    if settings.commercial:
        return app

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(DEV_FRONTEND_ORIGINS),
        allow_credentials=True,
        allow_methods=list(FRONTEND_CORS_METHODS),
        allow_headers=list(FRONTEND_CORS_HEADERS),
    )
    return app


def build_frontend_http_app(
    *,
    settings: RuntimeSettings | None = None,
    fiscal_operations_gateway_factory: Any | None = None,
    public_signup_enabled: bool = False,
    signup_verification_dispatcher: VerificationDispatcher | None = None,
    signup_credential_secret_reference: str = "env:FM_AI_SIGNUP_SECRET_KEY",
    commercial_access_gate_enabled: bool | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Constrói o HTTP ingress canônico + fronteiras WEB-PARITY para Next.js."""

    resolved_settings = settings or load_runtime_settings()

    engine = kwargs.get("engine") or build_engine(resolved_settings)
    session_factory = kwargs.get("session_factory") or build_session_factory(
        engine=engine,
        commercial=resolved_settings.commercial,
    )
    secret_store = kwargs.get("secret_store") or ReferenceSecretStore()
    auth_runtime = kwargs.get("auth_runtime") or AuthSessionRuntime(
        session_factory=session_factory,
        secret_store=secret_store,
    )

    billing_adapter_registry = kwargs.get(
        "commercial_billing_adapter_registry"
    ) or BillingProviderAdapterRegistryV1()

    kwargs["engine"] = engine
    kwargs["session_factory"] = session_factory
    kwargs["secret_store"] = secret_store
    kwargs["auth_runtime"] = auth_runtime
    kwargs["commercial_billing_adapter_registry"] = billing_adapter_registry

    app = build_http_app(settings=resolved_settings, **kwargs)
    gate_enabled = (
        resolved_settings.commercial_access_gate_enabled
        if commercial_access_gate_enabled is None
        else commercial_access_gate_enabled
    )
    commercial_access_app = AplicacaoAcessoComercialV1(
        session_factory,
        enforcement_enabled=gate_enabled,
    )

    @app.middleware("http")
    async def commercial_access_gate(request: Request, call_next):
        if not gate_enabled or not request.url.path.startswith("/v1/"):
            return await call_next(request)
        if request.url.path.startswith(
            (
                "/v1/auth",
                "/v1/public",
                "/v1/commercial",
                "/v1/admin/commercial",
                "/v1/control-plane/fmcc",
            )
        ):
            return await call_next(request)
        try:
            with session_factory() as session:
                resolved = obter_identidade_operacional(
                    request,
                    session,
                    auth_runtime=auth_runtime,
                )
            access = commercial_access_app.avaliar(
                tenant_id=resolved.identidade.tenant_id
            )
        except ErroSeguranca:
            # A própria rota permanece autoridade da resposta de autenticação.
            return await call_next(request)
        if not access.operational_allowed:
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content={
                    "erro": "commercial_access_restricted",
                    "access_mode": (
                        access.access_mode.value
                        if access.access_mode is not None
                        else "blocked"
                    ),
                    "reason": access.reason,
                    "revision": access.revision,
                },
            )
        return await call_next(request)

    app.include_router(
        build_fmcc_commercial_control_router(
            session_factory=session_factory,
            control_plane_token=resolved_settings.fmcc_control_plane_token,
        )
    )
    app.include_router(
        build_commercial_access_router(
            session_factory=session_factory,
            auth_runtime=auth_runtime,
            enforcement_enabled=gate_enabled,
            billing_adapter_registry=billing_adapter_registry,
            billing_secret_store=secret_store,
            billing_environment=(
                BillingEnvironment.PRODUCTION
                if resolved_settings.environment is RuntimeEnvironment.PRODUCTION
                else BillingEnvironment.SANDBOX
            ),
        )
    )
    app.include_router(
        build_public_signup_router(
            session_factory=session_factory,
            secret_store=secret_store,
            enabled=public_signup_enabled,
            verification_dispatcher=signup_verification_dispatcher,
            credential_secret_reference=signup_credential_secret_reference,
        )
    )
    for router_builder in (
        build_admin_auditoria_router,
        build_admin_backoffice_router,
        build_admin_comercial_router,
        build_admin_configuracao_router,
        build_admin_impressao_router,
        build_admin_integracoes_router,
        build_admin_notificacoes_router,
        build_admin_assistente_atendimento_router,
        build_admin_dashboard_router,
        build_admin_empresa_router,
        build_admin_usuarios_router,
        build_ai_finops_router,
        build_cardapio_publico_router,
        build_central_pedidos_router,
        build_crm_router,
        build_delivery_router,
        build_entrega_router,
    ):
        app.include_router(
            router_builder(
                session_factory=session_factory,
                auth_runtime=auth_runtime,
            )
        )
    app.include_router(
        build_admin_fiscal_router(
            session_factory=session_factory,
            auth_runtime=auth_runtime,
            operations_gateway_factory=fiscal_operations_gateway_factory,
        )
    )
    app.include_router(
        build_marketplaces_web_router(
            session_factory=session_factory,
            auth_runtime=auth_runtime,
        )
    )
    app.include_router(
        build_garcom_web_router(
            session_factory=session_factory,
            auth_runtime=auth_runtime,
        )
    )
    app.include_router(
        build_gerente_ia_web_router(
            session_factory=session_factory,
            auth_runtime=auth_runtime,
            secret_store=secret_store,
        )
    )
    app.include_router(
        build_pagamentos_web_router(
            session_factory=session_factory,
            auth_runtime=auth_runtime,
            secret_store=secret_store,
        )
    )
    return _configure_frontend_cors(app, settings=resolved_settings)
