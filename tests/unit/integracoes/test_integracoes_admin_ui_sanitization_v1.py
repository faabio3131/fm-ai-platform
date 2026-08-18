from __future__ import annotations

from pathlib import Path


UI_PATH = Path("infra/streamlit_app/integracoes_admin.py")


def test_integracoes_admin_nao_expoe_nome_de_classe_de_excecao_na_ui() -> None:
    source = UI_PATH.read_text(encoding="utf-8")

    assert "type(exc).__name__" not in source
    assert "Falha inesperada de validação:" not in source
    assert "Não foi possível salvar a configuração:" not in source
    assert "Não foi possível homologar:" not in source


def test_integracoes_admin_compila_apos_hardening_de_mensagens() -> None:
    source = UI_PATH.read_text(encoding="utf-8")
    compile(source, str(UI_PATH), "exec")
