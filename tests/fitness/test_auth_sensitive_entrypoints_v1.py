from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_auth_runtime_has_no_temporary_diagnostics() -> None:
    source = _text("infra/streamlit_app/auth_ui.py")
    assert "FM_AI_AUTH_DIAGNOSTICS" not in source
    assert "_auth_diagnostics_enabled" not in source
    assert "DIAG_" not in source


def test_admin_entrypoint_requires_login_and_sensitive_reauthentication() -> None:
    source = _text("pages/6_Administracao_Proprietario.py")
    assert "require_authentication(" in source
    assert "require_sensitive_reauthentication(" in source


def test_integrations_entrypoint_requires_login_pin_and_specific_permission() -> None:
    source = _text("pages/7_Integracoes_e_Credenciais.py")
    assert "require_authentication(" in source
    assert "require_sensitive_reauthentication(" in source
    assert "required_permission=Permissao.INTEGRACAO_GERENCIAR" in source


def test_sensitive_gate_blocks_runtime_local_identity() -> None:
    source = _text("infra/streamlit_app/auth_ui.py")
    assert 'identity.usuario_id == "runtime-local"' in source
    assert "not _auth_required(settings)" in source
    assert "Acesso administrativo sensível bloqueado" in source


def test_sensitive_idle_watchdog_is_frameless_and_reports_real_activity() -> None:
    source = _text("infra/streamlit_app/sensitive_idle_watchdog.py")
    assert "st.components.v2.component(" in source
    assert "streamlit.components.v1" not in source
    assert "components.html(" not in source
    assert 'setTriggerValue("activity"' in source
    assert 'setTriggerValue("expired"' in source
    assert "document.addEventListener" in source


def test_sensitive_grant_is_not_renewed_by_automatic_reruns() -> None:
    source = _text("infra/streamlit_app/auth_ui.py")
    start = source.index("def _sensitive_auth_valid")
    end = source.index("def record_sensitive_activity")
    validation_block = source[start:end]
    assert 'grant["last_activity_at"] = now' not in validation_block
    assert "def record_sensitive_activity" in source
