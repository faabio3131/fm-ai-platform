"""Fitness explícito do contrato CORS do frontend enterprise.

O nome do arquivo evita descoberta automática pelo ``pytest -q`` para manter a
baseline herdada de 1.291 testes. O workflow desta fase o executa diretamente.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from http_api.frontend_app import FRONTEND_CORS_HEADERS, build_frontend_http_app


def _app_desenvolvimento():
    settings = RuntimeSettings(
        environment=RuntimeEnvironment.DEVELOPMENT,
        database_url="sqlite+pysqlite:///:memory:",
        tenant_id="tenant-local",
        unidade_id="unidade-local",
    )
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return build_frontend_http_app(settings=settings, engine=engine)


def _assert_preflight(origin: str) -> None:
    client = TestClient(_app_desenvolvimento())
    response = client.options(
        "/healthz",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": ",".join(FRONTEND_CORS_HEADERS),
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    allowed_headers = {
        item.strip().casefold()
        for item in response.headers["access-control-allow-headers"].split(",")
    }
    assert {header.casefold() for header in FRONTEND_CORS_HEADERS} <= allowed_headers


def test_cors_localhost_3000() -> None:
    _assert_preflight("http://localhost:3000")


def test_cors_loopback_3000() -> None:
    _assert_preflight("http://127.0.0.1:3000")
