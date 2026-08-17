"""Watchdog visual do timeout das áreas administrativas sensíveis.

A proteção usa duas camadas independentes:
1. fragmento periódico do Streamlit para validar o grant no servidor;
2. temporizador no navegador que força reload após o prazo de inatividade.

O reload é intencional: impede que conteúdo já renderizado permaneça visível ou
editável quando a sessão sensível expira.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

from core.seguranca.autenticacao import IdentidadeUsuario
from infra.streamlit_app.auth_ui import lock_sensitive_area, sensitive_grant_is_valid

_SENSITIVE_AUTH_KEY = "_fm_ai_sensitive_auth_v1"
_WATCHDOG_INTERVAL_SECONDS = 5
_BROWSER_IDLE_RELOAD_MS = 181_000


def _watchdog_check(identity: IdentidadeUsuario, *, now: datetime | None = None) -> bool:
    """Retorna True quando o grant expirou e a tela deve ser bloqueada."""

    grant = st.session_state.get(_SENSITIVE_AUTH_KEY)
    return not sensitive_grant_is_valid(
        grant,
        identity,
        now=now or datetime.now(timezone.utc),
    )


def _watchdog_body(identity: IdentidadeUsuario) -> None:
    if _watchdog_check(identity):
        lock_sensitive_area()
        st.rerun()


def _render_browser_idle_reload() -> None:
    """Força reload no browser após 3 min sem um rerun normal da página."""

    components.html(
        f"""
        <script>
        (() => {{
            const timeoutMs = {_BROWSER_IDLE_RELOAD_MS};
            const timer = window.setTimeout(() => {{
                try {{
                    window.parent.location.reload();
                }} catch (e) {{
                    window.location.reload();
                }}
            }}, timeoutMs);
            window.addEventListener('beforeunload', () => window.clearTimeout(timer));
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def render_sensitive_idle_watchdog(identity: IdentidadeUsuario) -> None:
    """Fecha visualmente a área sensível após o período de inatividade."""

    _render_browser_idle_reload()

    fragment = getattr(st, "fragment", None)
    if fragment is None:
        fragment = getattr(st, "experimental_fragment", None)
    if fragment is None:
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
