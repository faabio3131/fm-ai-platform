"""Watchdog visual do timeout das áreas administrativas sensíveis.

O relógio de 3 minutos roda no navegador e é renovado somente por atividade real
do usuário: digitação, alteração de campos, clique/toque e rolagem. Reruns automáticos
do Streamlit não contam como atividade.

Quando o limite ocioso é atingido, o watchdog aciona o mesmo botão de bloqueio manual
da barra lateral. Isso limpa o grant no servidor e rerenderiza a página protegida.
"""

from __future__ import annotations

from datetime import datetime
import json

import streamlit as st
import streamlit.components.v1 as components

from core.seguranca.autenticacao import IdentidadeUsuario

_SENSITIVE_AUTH_KEY = "_fm_ai_sensitive_auth_v1"
_BROWSER_IDLE_TIMEOUT_MS = 180_000
_BROWSER_CHECK_INTERVAL_MS = 1_000


def _grant_marker(identity: IdentidadeUsuario) -> str:
    """Identifica a geração/atividade conhecida do grant sem expor qualquer segredo."""

    grant = st.session_state.get(_SENSITIVE_AUTH_KEY)
    if not isinstance(grant, dict) or grant.get("usuario_id") != identity.usuario_id:
        return "locked"
    last_activity_at = grant.get("last_activity_at")
    if isinstance(last_activity_at, datetime):
        return f"{identity.usuario_id}:{last_activity_at.isoformat()}"
    return f"{identity.usuario_id}:unknown"


def _render_browser_idle_watchdog(identity: IdentidadeUsuario) -> None:
    """Bloqueia após 3 minutos sem atividade REAL no documento principal."""

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
            const stateKey = '__fmAiSensitiveIdleV3';

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

            const lockSensitiveArea = () => {{
                const buttons = Array.from(parentDocument.querySelectorAll('button'));
                const lockButton = buttons.find((button) =>
                    (button.innerText || button.textContent || '').includes('Bloquear área administrativa agora')
                );
                if (lockButton) {{
                    lockButton.click();
                    return;
                }}
                // Fallback fail-closed: força rerun completo; o gate do servidor
                // revalida o grant antes de renderizar novamente a área sensível.
                parentWindow.location.reload();
            }};

            const intervalId = parentWindow.setInterval(() => {{
                if (state.expired) return;
                if ((Date.now() - state.lastRealActivityAt) >= timeoutMs) {{
                    state.expired = true;
                    lockSensitiveArea();
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
