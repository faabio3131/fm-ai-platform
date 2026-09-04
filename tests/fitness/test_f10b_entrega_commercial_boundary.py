from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "core" / "entrega" / "ui_streamlit.py"
PAGE = ROOT / "pages" / "9_Expedicao_Entrega.py"
E2E_APP = ROOT / "tests" / "e2e-entrega" / "app_entrega.py"


def test_ui_comercial_nao_depende_de_runtime_teste() -> None:
    text = UI.read_text(encoding="utf-8")
    assert "runtime_teste" not in text
    assert "contexto_entrega_teste" not in text
    assert "tenant-e2e" not in text
    assert "unidade-e2e" not in text
    assert "driver-1" not in text


def test_ui_resolve_identidade_real_e_injecao_so_em_teste() -> None:
    text = UI.read_text(encoding="utf-8")
    assert "IdentidadeUsuario" in text
    assert "_fm_ai_authenticated_identity_v1" in text
    assert ".contexto(" in text
    assert "contexto_injetado_so_permitido_em_teste" in text
    assert 'os.getenv("FM_AI_TEST_MODE") != "1"' in text


def test_pagina_comercial_exige_auth_rbac_e_flag() -> None:
    text = PAGE.read_text(encoding="utf-8")
    assert "require_authentication" in text
    assert "Permissao.EXPEDICAO_OPERAR" in text
    assert "entrega_v1_enabled" in text
    assert "render_entrega(session_factory=session_factory)" in text
    assert "st.query_params" not in text
    assert "runtime_teste" not in text


def test_runtime_historico_fica_isolado_no_e2e() -> None:
    text = E2E_APP.read_text(encoding="utf-8")
    assert 'FM_AI_TEST_MODE") != "1"' in text
    assert "contexto_entrega_teste" in text
    assert "render_entrega(session_factory=SessionLocal, contexto=contexto)" in text
