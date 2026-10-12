"""ASGI canônico do Kordena para a homologação Render.

Sem defaults de banco/tenant/unidade, seed de demonstração ou desativação de
RBAC. Falha no startup caso FM_AI_ENV != staging ou configuração esteja ausente.
"""
from __future__ import annotations

from core.runtime.config import RuntimeEnvironment, load_runtime_settings
from http_api.frontend_app import build_frontend_http_app

settings = load_runtime_settings()
if settings.environment != RuntimeEnvironment.STAGING:
    raise RuntimeError("Este entrypoint exige FM_AI_ENV=staging.")
if settings.allow_sqlite_commercial:
    raise RuntimeError("A homologação Render exige PostgreSQL; SQLite proibido.")

app = build_frontend_http_app(settings=settings)
