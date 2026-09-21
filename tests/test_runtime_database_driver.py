from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.runtime.database import build_engine


def _settings(database_url: str) -> RuntimeSettings:
    return RuntimeSettings(
        environment=RuntimeEnvironment.STAGING,
        database_url=database_url,
        tenant_id="tenant-staging",
        unidade_id="unidade-staging",
    )


def test_postgresql_url_uses_psycopg3_driver() -> None:
    engine = build_engine(_settings("postgresql://user:pass@localhost:5432/kordena"))
    try:
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()


def test_legacy_postgres_url_uses_psycopg3_driver() -> None:
    engine = build_engine(_settings("postgres://user:pass@localhost:5432/kordena"))
    try:
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()
