"""Fitness F7: test-runtime nunca pode ser o composition root comercial."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _texto(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_api_salao_nao_importa_runtime_teste() -> None:
    source = _texto("core/salao/__init__.py")
    assert "runtime_teste" not in source
    assert "contexto_salao_teste" not in source
    assert "preparar_schema_teste" not in source


def test_public_api_garcom_nao_importa_runtime_teste() -> None:
    source = _texto("core/garcom/__init__.py")
    assert "runtime_teste" not in source
    assert "contexto_garcom_teste" not in source
    assert "preparar_schema_teste" not in source


def test_renderers_comerciais_nao_referenciam_harness_teste() -> None:
    for path in ("core/salao/ui_streamlit.py", "core/garcom/ui_streamlit.py"):
        source = _texto(path)
        assert "runtime_teste" not in source
        assert "contexto_salao_teste" not in source
        assert "contexto_garcom_teste" not in source
        assert "preparar_schema_teste" not in source


def test_salao_comercial_nao_fabrica_pagamento_de_teste() -> None:
    ui = _texto("core/salao/ui_streamlit.py")
    app = _texto("application/salao_transacoes.py")
    assert "registrar_pagamento_confirmado_teste_v1" not in ui
    assert "registrar_pagamento_confirmado_teste_v1" not in app
    assert "runtime_teste" not in app
    assert "ui-pay-" not in ui
    assert "registrar_pagamento_confirmado(" in ui


def test_garcom_comercial_nao_escolhe_papel_por_widget() -> None:
    source = _texto("pages/8_Atendimento_Garcom.py")
    assert "require_authentication" in source
    assert "assert_schema_current" in source
    assert "st.query_params" not in source
    assert "papel=" not in source
    assert "usuario_id=" not in source


def test_migration_salao_teste_nao_entra_no_runner_oficial() -> None:
    source = _texto("migrations/runner.py")
    assert "0012_restaurant_operations_runtime_v1" in source
    assert "SalaoBase.metadata.create_all" in source
    assert "migrations.salao_v1" not in source
