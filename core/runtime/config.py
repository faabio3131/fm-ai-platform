"""Configuração explícita de ambiente da V1.

O objetivo é impedir que a aplicação comercial herde silenciosamente defaults de
laboratório. Desenvolvimento continua simples; produção exige configuração
explícita de banco servidor e identidade da unidade.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class RuntimeEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


_TRUE_VALUES = {"1", "true", "yes", "on"}
_ENV_ALIASES = {
    "dev": RuntimeEnvironment.DEVELOPMENT,
    "development": RuntimeEnvironment.DEVELOPMENT,
    "test": RuntimeEnvironment.TEST,
    "testing": RuntimeEnvironment.TEST,
    "stage": RuntimeEnvironment.STAGING,
    "staging": RuntimeEnvironment.STAGING,
    "prod": RuntimeEnvironment.PRODUCTION,
    "production": RuntimeEnvironment.PRODUCTION,
}


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _normalizar_ambiente() -> RuntimeEnvironment:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        return RuntimeEnvironment.TEST
    raw = os.getenv("FM_AI_ENV", "development").strip().lower()
    try:
        return _ENV_ALIASES[raw]
    except KeyError as exc:
        raise RuntimeError(
            "FM_AI_ENV invalido. Use development, test, staging ou production."
        ) from exc


@dataclass(frozen=True)
class RuntimeSettings:
    environment: RuntimeEnvironment
    database_url: str
    tenant_id: str
    unidade_id: str
    allow_sqlite_commercial: bool = False

    @property
    def commercial(self) -> bool:
        return self.environment in {
            RuntimeEnvironment.STAGING,
            RuntimeEnvironment.PRODUCTION,
        }

    @property
    def test(self) -> bool:
        return self.environment is RuntimeEnvironment.TEST

    def validate(self) -> "RuntimeSettings":
        url = self.database_url.strip()
        if not url:
            raise RuntimeError("DATABASE_URL nao definida para o runtime atual.")

        if self.commercial:
            if not self.tenant_id.strip() or not self.unidade_id.strip():
                raise RuntimeError(
                    "FM_AI_TENANT_ID e FM_AI_UNIDADE_ID sao obrigatorios em runtime comercial."
                )
            if url.lower().startswith("sqlite") and not self.allow_sqlite_commercial:
                raise RuntimeError(
                    "SQLite local nao e permitido em staging/production. Configure DATABASE_URL "
                    "para um banco servidor ou use FM_AI_ALLOW_SQLITE_COMMERCIAL=1 somente em "
                    "homologacao controlada."
                )
        return self


def load_runtime_settings(*, test_database_url: str | None = None) -> RuntimeSettings:
    """Carrega e valida o contrato de runtime a partir do ambiente.

    ``test_database_url`` permite que o harness E2E injete seu SQLite temporario sem
    contaminar a configuracao comercial.
    """

    environment = _normalizar_ambiente()
    if environment is RuntimeEnvironment.TEST and test_database_url:
        database_url = test_database_url
    else:
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url and environment is RuntimeEnvironment.DEVELOPMENT:
            database_url = "sqlite:///./banco_erp_local.db"

    commercial = environment in {
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.PRODUCTION,
    }
    tenant_default = "" if commercial else "tenant-local"
    unidade_default = "" if commercial else "unidade-local"
    settings = RuntimeSettings(
        environment=environment,
        database_url=database_url,
        tenant_id=os.getenv("FM_AI_TENANT_ID", tenant_default).strip(),
        unidade_id=os.getenv("FM_AI_UNIDADE_ID", unidade_default).strip(),
        allow_sqlite_commercial=_bool_env("FM_AI_ALLOW_SQLITE_COMMERCIAL"),
    )
    return settings.validate()
