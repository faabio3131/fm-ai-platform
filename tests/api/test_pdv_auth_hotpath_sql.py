"""Regressões de segurança e carga SQL da sessão no caminho operacional."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import http_api.auth as auth_module
from application.commercial_access import AplicacaoAcessoComercialV1
from http_api.auth import AuthSessionRuntime
from scripts import cleanup_expired_operational_sessions as maintenance
from tests.api.test_auth_http_contract import _infra as auth_infra
from tests.api.test_auth_http_contract import _login as auth_login
from tests.api.test_commercial_access_http_contract import _client as commercial_client
from tests.api.test_commercial_access_http_contract import _login as commercial_login


def test_auth_session_http_no_delete_during_login_or_me(monkeypatch):
    client = auth_infra(monkeypatch)
    queries = []

    def observer(conn, cursor, statement, params, context, many):
        queries.append(statement)

    event.listen(Engine, "before_cursor_execute", observer)
    try:
        assert auth_login(client).status_code == 200
        assert client.get("/v1/auth/me").status_code == 200
        assert client.get("/v1/auth/me").status_code == 200
    finally:
        event.remove(Engine, "before_cursor_execute", observer)
    assert not any(
        statement.lstrip().upper().startswith("DELETE")
        and "fm_operational_sessions_v1" in statement
        for statement in queries
    )


def test_commercial_gate_resolves_identity_only_once_per_request(monkeypatch):
    client = commercial_client(monkeypatch)
    commercial_login(client)
    monkeypatch.setattr(
        AplicacaoAcessoComercialV1, "avaliar",
        lambda self, *, tenant_id: SimpleNamespace(operational_allowed=True),
    )
    counter = {"calls": 0}
    original = AuthSessionRuntime.resolver_identidade

    def counted(self, request):
        counter["calls"] += 1
        return original(self, request)

    monkeypatch.setattr(AuthSessionRuntime, "resolver_identidade", counted)
    # Sem mapping da loja, a rota pode responder 403; a identidade deve
    # ser resolvida uma vez, e a autorização de produto permanece na rota.
    result = client.get("/v1/pdv/produtos")
    assert result.status_code in (200, 403)
    assert counter["calls"] == 1
    client.get("/v1/pdv/produtos")
    assert counter["calls"] == 2  # nunca compartilhado entre requests


def test_expired_session_is_rejected_without_delete(monkeypatch):
    client = auth_infra(monkeypatch)
    monkeypatch.setattr(auth_module, "_SESSION_TTL_SECONDS", -1)
    queries = []

    def observer(conn, cursor, statement, params, context, many):
        queries.append(statement)

    event.listen(Engine, "before_cursor_execute", observer)
    try:
        assert auth_login(client).status_code == 200
        assert client.get("/v1/auth/me").status_code == 401
    finally:
        event.remove(Engine, "before_cursor_execute", observer)
    assert not any(
        statement.lstrip().upper().startswith("DELETE")
        and "fm_operational_sessions_v1" in statement
        for statement in queries
    )


def test_dedicated_maintenance_deletes_only_expired_sessions(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from migrations.runner import run_migrations

    run_migrations(engine)
    with engine.begin() as conn:
        now = datetime.now(UTC)
        for sid, expires in (
            ("expired-test", now - timedelta(minutes=2)),
            ("live-test", now + timedelta(hours=2)),
        ):
            conn.execute(
                text(
                    "INSERT INTO fm_operational_sessions_v1 "
                    "(session_id, usuario_id, identity_user_id, membership_id, "
                    "email, tenant_id, unidade_ativa_id, expira_em) "
                    "VALUES (:sid, 'u', 'i', 'm', 'user@example.com', "
                    "'tenant', 'unit', :expires)"
                ),
                {"sid": sid, "expires": expires},
            )
    monkeypatch.setattr(maintenance, "build_engine", lambda settings: engine)
    monkeypatch.setattr(maintenance, "load_runtime_settings", lambda: None)
    try:
        assert maintenance.cleanup() == 1
        with Session(engine) as session:
            rows = session.execute(
                text("SELECT session_id FROM fm_operational_sessions_v1")
            ).all()
            assert [row[0] for row in rows] == ["live-test"]
    finally:
        engine.dispose()
