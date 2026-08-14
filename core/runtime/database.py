"""Fábrica de engine para desenvolvimento, teste e produção.

Centraliza pool, healthcheck e diferenças entre SQLite e bancos servidor. Isso
remove a criação de engine ad-hoc do app e prepara DB-001 para migrações e
observabilidade de infraestrutura.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text

from .config import RuntimeSettings


@dataclass(frozen=True)
class DatabaseHealth:
    ok: bool
    backend: str
    detail: str


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} deve ser inteiro") from exc
    if value < minimum:
        raise RuntimeError(f"{name} deve ser >= {minimum}")
    return value


def build_engine(settings: RuntimeSettings) -> Engine:
    """Cria engine com política adequada ao backend.

    SQLite continua suportado em desenvolvimento/teste. Em banco servidor,
    habilitamos pre-ping, reciclagem de conexões e limites de pool configuráveis.
    """

    url = settings.database_url
    is_sqlite = url.lower().startswith("sqlite")
    common: dict[str, object] = {"pool_pre_ping": True}

    if is_sqlite:
        common["connect_args"] = {"check_same_thread": False}
    else:
        common.update(
            {
                "pool_size": _int_env("FM_AI_DB_POOL_SIZE", 10, 1),
                "max_overflow": _int_env("FM_AI_DB_MAX_OVERFLOW", 20, 0),
                "pool_recycle": _int_env("FM_AI_DB_POOL_RECYCLE_SECONDS", 1800, 60),
            }
        )

    return create_engine(url, **common)


def check_database_health(engine: Engine) -> DatabaseHealth:
    backend = engine.url.get_backend_name()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return DatabaseHealth(True, backend, "database_ready")
    except Exception as exc:  # noqa: BLE001 - fronteira de infraestrutura
        return DatabaseHealth(False, backend, f"database_unavailable:{type(exc).__name__}")
