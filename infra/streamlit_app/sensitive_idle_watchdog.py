"""Watchdog visual do timeout das áreas administrativas sensíveis.

A proteção combina duas camadas:
1. fragmento periódico do Streamlit para validar o grant no servidor;
2. relógio de inatividade no navegador, renovado somente por atividade real do usuário.

O navegador não usa um prazo fixo desde o desbloqueio. Digitação, clique, toque,
rolagem ou alteração de campo renovam o relógio. Reruns automáticos do Streamlit não
contam como atividade do usuário e, portanto, não mantêm a área aberta sozinhos.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json

import streamlit as st
import streamlit.components.v1 as components

from core.seguranca.autenticacao import IdentidadeUsuario
from infra.streamlit_app.auth_ui import lock_sensitive_area, sensitive_grant_is_valid

_SENSITIVE_AUTH_KEY = "_fm_ai_sensitive_auth_v1"
_WATCHDOG_INTERVAL_SECONDS = 5
_BROWSER_IDLE_TIMEOUT_MS = 180_000
_BROWSER_CHECK_INTERVAL_MS = 1_000


def _watchdog_check(identity: IdentidadeUsuario, *, now: datetime | None = None) -> bool:
    """Retorna True quando o grant do servidor expirou e a tela deve ser bloqueada."""

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


def _grant_marker(identity: IdentidadeUsuario) -> str:
    """Identifica a geração/atividade real conhecida do grant sem expor segredo."""

    grant = st.session_state.get(_SENSITIVE_AUTH_KEY)
    if not isinstance(grant, dict) or grant.get("usuario_id") != identity.usuario_id:
        return "locked"
    last_activity_at = grant.get("last_activity_at")
    if isinstance(last_activity_at, datetime):
        return f"{identity.usuario_id}:{last_activity_at.isoformat()}"
    return f"{identity.usuario_id}:unknown"


def _render_browser_idle_watchdog(identity: IdentidadeUsuario) -> None:
    """Bloqueia após 3 min sem atividade REAL no documento principal do navegador."""

    marker = json.dumps(_grant_marker(identity))
    components.html(
        f"""
        <script>
        (() => {{
            const parentWindow = window.parent;
            const parentDocument = parentWindow.document;
            const marker = {marker};
            const timeoutMs = {_BROWSER_IDLE_TIMEOUT_MS};
            const checkEveryMs = {_BROWSER_CHECK_INTERVAL_MS};
            const stateKey = '__fmAiSensitiveIdleV2';

            let state = parentWindow[stateKey];
            if (!state || state.marker !== marker) {{
                if (state && state.cleanup) {{
                    try {{ state.cleanup(); }} catch (_) {{}}
                }}
                state = {{
                    marker,
                    lastRealActivityAt: Date.now(),
                    expired: false,
                    cleanup: null,
                }};
                parentWindow[stateKey] = state;
            }}

            const markRealActivity = () => {{
                if (state.expired) return;
                state.lastRealActivityAt = Date.now();
            }};

            const events = ['keydown', 'input', 'change', 'pointerdown', 'touchstart', 'wheel', 'scroll'];
            for (const eventName of events) {{
                parentDocument.addEventListener(eventName, markRealActivity, {{capture: true, passive: true}});
            }}

            const intervalId = parentWindow.setInterval(() => {{
                if (state.expired) return;
                if ((Date.now() - state.lastRealActivityAt) >= timeoutMs) {{
                    state.expired = true;
                    try {{
                        parentWindow.location.reload();
                    }} catch (_) {{
                        window.location.reload();
                    }}
                }}
            }}, checkEveryMs);

            state.cleanup = () => {{
                parentWindow.clearInterval(intervalId);
                for (const eventName of events) {{
                    parentDocument.removeEventListener(eventName, markRealActivity, {{capture: true}});
                }}
            }};
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def render_sensitive_idle_watchdog(identity: IdentidadeUsuario) -> None:
    """Mantém a área aberta enquanto há uso real e a fecha após 3 min ociosa."""

    _render_browser_idle_watchdog(identity)

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
