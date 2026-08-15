"""Gate de autenticação da aplicação Streamlit comercial."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.autenticacao import IdentidadeUsuario, ServicoAutenticacao
from core.seguranca.erros import CredenciaisInvalidas, UsuarioInativo
from core.seguranca.permissoes import Papel, Permissao
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

_TRUE_VALUES = {"1", "true", "yes", "on"}
_SESSION_KEY = "_fm_ai_authenticated_identity_v1"
_FAILED_KEY = "_fm_ai_auth_failed_attempts_v1"
_BLOCKED_UNTIL_KEY = "_fm_ai_auth_blocked_until_v1"
_SENSITIVE_AUTH_KEY = "_fm_ai_sensitive_auth_v1"
_SENSITIVE_FAILED_KEY = "_fm_ai_sensitive_auth_failed_attempts_v1"
_SENSITIVE_BLOCKED_UNTIL_KEY = "_fm_ai_sensitive_auth_blocked_until_v1"
_MAX_ATTEMPTS = 5
_BLOCK_SECONDS = 30
_SENSITIVE_BLOCK_SECONDS = 60
_SENSITIVE_TTL_SECONDS = 600
_SENSITIVE_ROLES = frozenset({Papel.ADMINISTRADOR, Papel.GERENTE})


def _auth_required(settings: RuntimeSettings) -> bool:
    if settings.environment in {
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.PRODUCTION,
    }:
        return True
    value = os.getenv("FM_AI_AUTH_V1", "0").strip().lower()
    return value in _TRUE_VALUES


def _development_identity(settings: RuntimeSettings) -> IdentidadeUsuario:
    """Identidade explícita de desenvolvimento/teste, nunca usada em produção."""

    return IdentidadeUsuario(
        usuario_id="runtime-local",
        email="runtime-local@fm.ai",
        senha_hash="runtime-local-no-login",
        tenant_id=settings.tenant_id,
        unidade_id=settings.unidade_id,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        unidades_permitidas=frozenset({settings.unidade_id}),
        ativo=True,
    )


def can_access_sensitive_area(
    identity: IdentidadeUsuario,
    *,
    required_permission: Permissao | None = None,
) -> bool:
    """Decide autorização de entrada sem confundir papel com permissão da seção.

    A área Administração/Proprietário exige papel privilegiado. Cada subseção pode
    acrescentar sua própria permissão (por exemplo, integrações) sem transformar
    ``integracao.gerenciar`` em uma chave universal de toda a administração.
    """

    if not identity.ativo or not (identity.papeis & _SENSITIVE_ROLES):
        return False
    if required_permission is None:
        return True
    return required_permission in identity.permissoes


def _blocked_until() -> datetime | None:
    value = st.session_state.get(_BLOCKED_UNTIL_KEY)
    return value if isinstance(value, datetime) else None


def _register_failure() -> None:
    attempts = int(st.session_state.get(_FAILED_KEY, 0)) + 1
    st.session_state[_FAILED_KEY] = attempts
    if attempts >= _MAX_ATTEMPTS:
        st.session_state[_BLOCKED_UNTIL_KEY] = datetime.now(timezone.utc) + timedelta(
            seconds=_BLOCK_SECONDS
        )
        st.session_state[_FAILED_KEY] = 0


def _clear_failures() -> None:
    st.session_state.pop(_FAILED_KEY, None)
    st.session_state.pop(_BLOCKED_UNTIL_KEY, None)


def _sensitive_blocked_until() -> datetime | None:
    value = st.session_state.get(_SENSITIVE_BLOCKED_UNTIL_KEY)
    return value if isinstance(value, datetime) else None


def _register_sensitive_failure() -> None:
    attempts = int(st.session_state.get(_SENSITIVE_FAILED_KEY, 0)) + 1
    st.session_state[_SENSITIVE_FAILED_KEY] = attempts
    if attempts >= _MAX_ATTEMPTS:
        st.session_state[_SENSITIVE_BLOCKED_UNTIL_KEY] = datetime.now(
            timezone.utc
        ) + timedelta(seconds=_SENSITIVE_BLOCK_SECONDS)
        st.session_state[_SENSITIVE_FAILED_KEY] = 0


def _clear_sensitive_auth() -> None:
    st.session_state.pop(_SENSITIVE_AUTH_KEY, None)
    st.session_state.pop(_SENSITIVE_FAILED_KEY, None)
    st.session_state.pop(_SENSITIVE_BLOCKED_UNTIL_KEY, None)


def _sensitive_auth_valid(identity: IdentidadeUsuario) -> bool:
    grant = st.session_state.get(_SENSITIVE_AUTH_KEY)
    if not isinstance(grant, dict):
        return False
    expires_at = grant.get("expires_at")
    return bool(
        grant.get("usuario_id") == identity.usuario_id
        and isinstance(expires_at, datetime)
        and expires_at > datetime.now(timezone.utc)
    )


def require_authentication(
    *,
    session_factory: Callable[[], Session],
    settings: RuntimeSettings,
) -> IdentidadeUsuario:
    """Exige login em runtime comercial e retorna identidade autenticada."""

    existing = st.session_state.get(_SESSION_KEY)
    if isinstance(existing, IdentidadeUsuario) and existing.ativo:
        return existing

    if not _auth_required(settings):
        identity = _development_identity(settings)
        st.session_state[_SESSION_KEY] = identity
        return identity

    st.title("🔐 Acesso ao Gerente AI")
    st.caption(
        "Entre com um usuário autorizado para a empresa e unidade configuradas."
    )

    blocked = _blocked_until()
    now = datetime.now(timezone.utc)
    if blocked is not None and blocked > now:
        remaining = max(1, int((blocked - now).total_seconds()))
        st.error(f"Muitas tentativas inválidas. Aguarde {remaining} segundos.")
        st.stop()
    if blocked is not None:
        _clear_failures()

    with st.form("fm_ai_login_v1", clear_on_submit=False):
        email = st.text_input("E-mail", autocomplete="email")
        password = st.text_input("Senha", type="password", autocomplete="current-password")
        submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    if submit:
        db = session_factory()
        try:
            auth = ServicoAutenticacao(RepositorioIdentidadesSQLAlchemy(db))
            identity = auth.autenticar(email=email, password=password)
            if identity.tenant_id != settings.tenant_id:
                raise CredenciaisInvalidas("credenciais invalidas")
            if settings.unidade_id not in identity.unidades_permitidas:
                raise CredenciaisInvalidas("credenciais invalidas")
            st.session_state[_SESSION_KEY] = identity
            _clear_failures()
            _clear_sensitive_auth()
            st.rerun()
        except (CredenciaisInvalidas, UsuarioInativo):
            _register_failure()
            st.error("E-mail ou senha inválidos, ou usuário sem acesso a esta unidade.")
        except SQLAlchemyError:
            st.error(
                "A autenticação comercial ainda não foi inicializada neste banco. "
                "Execute as migrations da V1 e crie o primeiro administrador."
            )
        finally:
            db.close()

    st.stop()
    raise RuntimeError("unreachable")


def require_sensitive_reauthentication(
    *,
    identity: IdentidadeUsuario,
    session_factory: Callable[[], Session],
    settings: RuntimeSettings,
    required_permission: Permissao | None = None,
) -> None:
    """Exige confirmação recente de senha para abrir áreas administrativas sensíveis."""

    if not can_access_sensitive_area(
        identity, required_permission=required_permission
    ):
        st.error(
            "Área restrita: seu usuário não possui autorização para esta seção administrativa."
        )
        st.stop()

    if identity.usuario_id == "runtime-local" or not _auth_required(settings):
        st.error(
            "Acesso administrativo sensível bloqueado para a identidade automática de "
            "desenvolvimento. Ative a autenticação V1 e entre com um usuário real "
            "de gerente ou proprietário/administrador."
        )
        st.stop()

    if _sensitive_auth_valid(identity):
        return

    blocked = _sensitive_blocked_until()
    now = datetime.now(timezone.utc)
    if blocked is not None and blocked > now:
        remaining = max(1, int((blocked - now).total_seconds()))
        st.error(
            f"Muitas tentativas de confirmação inválidas. Aguarde {remaining} segundos."
        )
        st.stop()
    if blocked is not None:
        _clear_sensitive_auth()

    st.warning(
        "Área protegida. Confirme novamente sua senha de gerente ou "
        "proprietário/administrador para continuar."
    )
    st.caption(f"Usuário autenticado: {identity.email}")
    with st.form("fm_ai_sensitive_reauth_v1", clear_on_submit=True):
        password = st.text_input(
            "Senha",
            type="password",
            autocomplete="current-password",
        )
        submit = st.form_submit_button(
            "Desbloquear por 10 minutos",
            type="primary",
            use_container_width=True,
        )

    if submit:
        db = session_factory()
        try:
            authenticated = ServicoAutenticacao(
                RepositorioIdentidadesSQLAlchemy(db)
            ).autenticar(email=identity.email, password=password)
            same_scope = (
                authenticated.usuario_id == identity.usuario_id
                and authenticated.tenant_id == identity.tenant_id
                and identity.unidade_id in authenticated.unidades_permitidas
            )
            privileged = can_access_sensitive_area(
                authenticated,
                required_permission=required_permission,
            )
            if not same_scope or not privileged:
                raise CredenciaisInvalidas("credenciais invalidas")
            st.session_state[_SENSITIVE_AUTH_KEY] = {
                "usuario_id": identity.usuario_id,
                "expires_at": datetime.now(timezone.utc)
                + timedelta(seconds=_SENSITIVE_TTL_SECONDS),
            }
            st.session_state.pop(_SENSITIVE_FAILED_KEY, None)
            st.session_state.pop(_SENSITIVE_BLOCKED_UNTIL_KEY, None)
            st.rerun()
        except (CredenciaisInvalidas, UsuarioInativo):
            _register_sensitive_failure()
            st.error("Senha inválida ou usuário sem autorização para esta área.")
        except SQLAlchemyError:
            st.error("Não foi possível validar a autorização neste momento.")
        finally:
            db.close()

    st.stop()


def render_identity_sidebar(
    identity: IdentidadeUsuario,
    settings: RuntimeSettings,
) -> None:
    st.success(f"Conectado como:\n**{identity.email}**")
    st.info(f"🏪 **Unidade ativa:**\n{settings.unidade_id}")
    papeis = ", ".join(sorted(papel.value for papel in identity.papeis))
    st.caption(f"Perfil: {papeis}")
    if can_access_sensitive_area(identity):
        st.page_link(
            "pages/6_Administracao_Proprietario.py",
            label="🔐 Administração / Proprietário",
            use_container_width=True,
        )
    if _auth_required(settings) and st.button("Sair", key="fm_ai_logout_v1"):
        st.session_state.pop(_SESSION_KEY, None)
        _clear_failures()
        _clear_sensitive_auth()
        st.rerun()
