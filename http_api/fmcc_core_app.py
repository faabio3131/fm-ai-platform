"""Dedicated FastAPI composition root for the shared FM Cognitive Core."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core.runtime import build_engine, check_database_health, load_runtime_settings
from core.runtime.config import RuntimeSettings
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from http_api.fmcc_core import build_fmcc_core_router
from infra.seguranca.session_guard import build_session_factory


def build_fmcc_core_app(
    *,
    settings: RuntimeSettings | None = None,
    engine: Engine | None = None,
    session_factory: Callable[[], Session] | None = None,
    secret_store: SecretStore | None = None,
) -> FastAPI:
    """Build only the internal shared-Core surface required by FMCC."""

    settings = settings or load_runtime_settings()
    engine = engine or build_engine(settings)
    session_factory = session_factory or build_session_factory(
        engine=engine,
        commercial=settings.commercial,
    )
    secret_store = secret_store or ReferenceSecretStore()

    app = FastAPI(
        title="FM Cognitive Core — Shared Service",
        version="1.0",
        docs_url=None if settings.commercial else "/docs",
        redoc_url=None,
        openapi_url=None if settings.commercial else "/openapi.json",
    )
    app.include_router(
        build_fmcc_core_router(
            session_factory=session_factory,
            secret_store=secret_store,
        )
    )

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> JSONResponse:
        health = check_database_health(engine)
        return JSONResponse(
            status_code=(
                status.HTTP_200_OK
                if health.ok
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            content={
                "ok": health.ok,
                "service": "fm-cognitive-core",
                "backend": health.backend,
                "detail": health.detail,
            },
        )

    return app
