"""Watchdog visual do timeout de inatividade das áreas administrativas sensíveis."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from core.seguranca.autenticacao import IdentidadeUsuario
from infra.streamlit_app.auth_ui import lock_sensitive_area, sensitive_grant_is_valid

_SENSITIVE_AUTH_KEY = "_fm_ai_sensitive_auth_v1"
_WATCHDOG_INTERVAL_SECONDS = 5


def _watchdog_check(identity: IdentidadeUsuario, *, now: datetime | None = None) -> bool:
    """Retorna True quando o grant expirou e deve bloquear a tela imediatamente."""

    grant = st.session_state.get(_SENSITIVE_AUTH_KEY)
    return not sensitive_grant_is_valid(
        grant,
        identity,
        now=now or datetime.now(timezone.utc),
    )


def _watchdog_body(identity: IdentidadeUsuario) -> None:
    if _watchdog_check(identity):
        lock_sensitive_area()
        # Rerun completo: remove imediatamente o conteúdo sensível já renderizado
        # e volta ao formulário de reautenticação antes de qualquer nova ação.
        st.rerun()


def render_sensitive_idle_watchdog(identity: IdentidadeUsuario) -> None:
    """Mantém um relógio independente que fecha visualmente a área após 3 min ociosa."""

    fragment = getattr(st, "fragment", None)
    if fragment is None:
        fragment = getattr(st, "experimental_fragment", None)
    if fragment is None:
        # Falha fechada: uma versão antiga do Streamlit não pode manter uma área
        # administrativa aberta sem mecanismo confiável de expiração visual.
        lock_sensitive_area()
        st.error(
            "A proteção automática por inatividade exige uma versão compatível do "
            "Streamlit. A área administrativa foi bloqueada por segurança."
        )
        st.stop()

    @fragment(run_every=_WATCHDOG_INTERVAL_SECONDS)
    def _sensitive_idle_watchdog_fragment() -> None:
        _watchdog_body(identity)

    _sensitive_idle_watchdog_fragment()
