"""Watchdog comercial do timeout das áreas administrativas sensíveis.

O relógio de 3 minutos roda no DOM principal por um Streamlit Component V2.
Somente atividade real do usuário renova o grant no servidor. Reruns automáticos
não contam como atividade. Ao expirar, o componente emite um trigger para Python,
que limpa o grant sensível antes do rerun da página protegida.
"""

from __future__ import annotations

import json
from datetime import datetime

import streamlit as st

from core.seguranca.autenticacao import IdentidadeUsuario
from infra.streamlit_app.auth_ui import (
    lock_sensitive_area,
    record_sensitive_activity,
)

_SENSITIVE_AUTH_KEY = "_fm_ai_sensitive_auth_v1"
_BROWSER_IDLE_TIMEOUT_MS = 180_000
_ACTIVITY_REPORT_INTERVAL_MS = 30_000

_SENSITIVE_IDLE_WATCHDOG_COMPONENT = st.components.v2.component(
    name="fm_ai_sensitive_idle_watchdog_v4",
    html='<span id="fm-ai-sensitive-idle-watchdog" hidden></span>',
    js="""
    export default function({ data, setTriggerValue }) {
        const marker = String(data.marker);
        const timeoutMs = Number(data.timeoutMs);
        const activityReportEveryMs = Number(data.activityReportEveryMs);
        const stateKey = "__fmAiSensitiveIdleV4";

        let state = window[stateKey];
        if (!state || state.marker !== marker) {
            if (state && state.cleanup) {
                try { state.cleanup(); } catch (_) {}
            }
            state = {
                marker,
                lastRealActivityAt: Date.now(),
                lastReportedActivityAt: Date.now(),
                expired: false,
                timeoutId: null,
                cleanup: null,
            };
            window[stateKey] = state;
        } else if (state.cleanup) {
            try { state.cleanup(); } catch (_) {}
            state.cleanup = null;
        }

        const clearTimer = () => {
            if (state.timeoutId !== null) {
                window.clearTimeout(state.timeoutId);
                state.timeoutId = null;
            }
        };

        const expireIfIdle = () => {
            if (state.expired) return;
            const idleForMs = Date.now() - state.lastRealActivityAt;
            const remainingMs = timeoutMs - idleForMs;
            if (remainingMs <= 0) {
                state.expired = true;
                clearTimer();
                setTriggerValue("expired", Date.now());
                return;
            }
            clearTimer();
            state.timeoutId = window.setTimeout(expireIfIdle, remainingMs);
        };

        const markRealActivity = () => {
            if (state.expired) return;
            const now = Date.now();
            state.lastRealActivityAt = now;

            if ((now - state.lastReportedActivityAt) >= activityReportEveryMs) {
                state.lastReportedActivityAt = now;
                setTriggerValue("activity", now);
            }
            expireIfIdle();
        };

        const events = [
            "keydown",
            "input",
            "change",
            "pointerdown",
            "touchstart",
            "wheel",
        ];
        for (const eventName of events) {
            document.addEventListener(eventName, markRealActivity, {
                capture: true,
                passive: true,
            });
        }

        expireIfIdle();

        const cleanup = () => {
            clearTimer();
            for (const eventName of events) {
                document.removeEventListener(eventName, markRealActivity, {
                    capture: true,
                });
            }
        };
        state.cleanup = cleanup;
        return cleanup;
    }
    """,
)


def _grant_marker(identity: IdentidadeUsuario) -> str:
    """Identifica a geração de atividade do grant sem expor segredo."""

    grant = st.session_state.get(_SENSITIVE_AUTH_KEY)
    if not isinstance(grant, dict) or grant.get("usuario_id") != identity.usuario_id:
        return "locked"
    last_activity_at = grant.get("last_activity_at")
    if isinstance(last_activity_at, datetime):
        return json.dumps(
            {
                "usuario_id": identity.usuario_id,
                "last_activity_at": last_activity_at.isoformat(),
            },
            sort_keys=True,
        )
    return "locked"


def _record_browser_activity(identity: IdentidadeUsuario) -> None:
    """Callback do browser: renova o grant somente se ainda for válido."""

    record_sensitive_activity(identity)


def render_sensitive_idle_watchdog(identity: IdentidadeUsuario) -> None:
    """Fecha a área após 3 min sem atividade real, inclusive sob reruns automáticos."""

    marker = _grant_marker(identity)
    if marker == "locked":
        lock_sensitive_area()
        st.rerun()

    _SENSITIVE_IDLE_WATCHDOG_COMPONENT(
        key=f"fm-ai-sensitive-idle-watchdog:{identity.usuario_id}",
        data={
            "marker": marker,
            "timeoutMs": _BROWSER_IDLE_TIMEOUT_MS,
            "activityReportEveryMs": _ACTIVITY_REPORT_INTERVAL_MS,
        },
        on_activity_change=lambda: _record_browser_activity(identity),
        on_expired_change=lock_sensitive_area,
    )
