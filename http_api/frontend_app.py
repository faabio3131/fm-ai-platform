"""FastAPI factory para o frontend enterprise desacoplado da V1.

Mantém o ``build_http_app`` como autoridade de rotas e adiciona apenas a
política CORS necessária ao workspace Next.js durante desenvolvimento/teste.
Ambientes comerciais permanecem fail-closed para origens localhost.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.runtime import load_runtime_settings
from core.runtime.config import RuntimeSettings
from http_api.app import build_http_app

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
    """Constrói o HTTP ingress canônico com CORS local para o Next.js."""

    resolved_settings = settings or load_runtime_settings()
    app = build_http_app(settings=resolved_settings, **kwargs)
    return _configure_frontend_cors(app, settings=resolved_settings)
