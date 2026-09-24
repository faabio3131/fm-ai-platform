from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel
from http_api import frontend_app
from http_api.auth import (
    _GerenciadorSessaoOperacional,
    _SessaoInvalida,
    build_auth_router,
)

SECRET = "kca14-session-hardening-secret-0123456789-abcdef"
TENANT = "tenant-kca14"
UNIT_A = "unit-kca14-a"
UNIT_B = "unit-kca14-b"


def _identity() -> IdentidadeUsuario:
    return IdentidadeUsuario(
        usuario_id="membership-kca14",
        email="security-kca14@example.com",
        senha_hash="hash-not-used-in-session-manager",
        tenant_id=TENANT,
        unidade_id=UNIT_A,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        unidades_permitidas=frozenset({UNIT_A, UNIT_B}),
        identity_user_id="identity-kca14",
        membership_id="membership-kca14",
        product_code="KORDENA",
    )


def test_session_fixation_is_not_accepted_and_each_session_has_fresh_token() -> None:
    manager = _GerenciadorSessaoOperacional(SECRET)
    _, first_token = manager.criar(_identity())
    _, second_token = manager.criar(_identity())

    assert first_token != second_token
    with pytest.raises(_SessaoInvalida):
        manager.resolver("attacker-fixed-session.attacker-signature")


def test_old_session_token_cannot_be_replayed_after_unit_switch() -> None:
    manager = _GerenciadorSessaoOperacional(SECRET)
    session, old_token = manager.criar(_identity())

    updated, new_token = manager.trocar_unidade(session, unidade_id=UNIT_B)

    with pytest.raises(_SessaoInvalida):
        manager.resolver(old_token)
    assert manager.resolver(new_token) == updated
    assert updated.unidade_ativa_id == UNIT_B


def test_old_session_token_cannot_be_replayed_after_admin_step_up() -> None:
    manager = _GerenciadorSessaoOperacional(SECRET)
    session, old_token = manager.criar(_identity())

    elevated, new_token = manager.elevar_admin(session)

    with pytest.raises(_SessaoInvalida):
        manager.resolver(old_token)
    assert manager.resolver(new_token) == elevated
    assert elevated.admin_elevado_ate is not None


def test_expired_session_is_removed_and_fails_closed() -> None:
    manager = _GerenciadorSessaoOperacional(SECRET)
    session, token = manager.criar(_identity())
    manager._sessions[session.session_id] = replace(
        session,
        expira_em=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    with pytest.raises(_SessaoInvalida):
        manager.resolver(token)
    assert session.session_id not in manager._sessions


def test_commercial_cookie_and_cors_policy_reduce_csrf_surface() -> None:
    auth_source = inspect.getsource(build_auth_router)
    cors_source = inspect.getsource(frontend_app._configure_frontend_cors)

    assert "httponly=True" in auth_source
    assert "secure=settings.commercial" in auth_source
    assert 'samesite="lax"' in auth_source
    assert "if settings.commercial:" in cors_source
    assert "return app" in cors_source
    assert "allow_credentials=True" in cors_source
