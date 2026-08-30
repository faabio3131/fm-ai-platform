from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


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
