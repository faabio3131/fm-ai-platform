"""FastAPI factory para o frontend enterprise desacoplado da V1.

Mantém o ``build_http_app`` como autoridade das rotas já promovidas e adiciona
as fronteiras WEB-PARITY em certificação usando exatamente o mesmo engine,
session factory, secret store e runtime de sessão autenticada. A política CORS
local continua restrita a desenvolvimento/teste; ambientes comerciais permanecem
fail-closed para origens localhost.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.runtime import build_engine, load_runtime_settings
from core.runtime.config import RuntimeSettings
from core.seguranca.segredos import ReferenceSecretStore
from http_api.admin_dashboard import build_admin_dashboard_router
from http_api.app import build_http_app
from http_api.auth import AuthSessionRuntime
from http_api.central_pedidos import build_central_pedidos_router
from http_api.crm import build_crm_router
from http_api.delivery import build_delivery_router
from http_api.entrega import build_entrega_router
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

    kwargs["engine"] = engine
    kwargs["session_factory"] = session_factory
    kwargs["secret_store"] = secret_store
    kwargs["auth_runtime"] = auth_runtime

    app = build_http_app(settings=resolved_settings, **kwargs)
    for router_builder in (
        build_admin_dashboard_router,
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
    return _configure_frontend_cors(app, settings=resolved_settings)
