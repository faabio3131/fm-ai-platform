from pathlib import Path


def test_dominio_nao_importa_frameworks_e_app_nao_ativa_pedido():
    textos = "\n".join(
        p.read_text(encoding="utf-8") for p in Path("core/dominio").glob("*.py")
    )
    assert "sqlalchemy" not in textos.lower()
    assert "streamlit" not in textos.lower()
    assert "import app" not in textos.lower()
    app = Path("app.py").read_text(encoding="utf-8")
    assert "core.pedidos" not in app


def test_repository_nao_oferece_hard_delete():
    texto = Path("core/pedidos/repositorios.py").read_text(encoding="utf-8")
    assert "def delete" not in texto
    assert "def excluir" not in texto
    assert "Session" not in texto


def test_harness_e2e_central_e_isolado_e_reusa_renderer():
    harness = Path("tests/e2e-orders-center/app_order_center.py").read_text(
        encoding="utf-8"
    )
    launcher = Path(
        "tests/e2e-orders-center/start-order-center-streamlit.cjs"
    ).read_text(encoding="utf-8")
    config = Path("playwright.order-center.config.ts").read_text(encoding="utf-8")

    assert "from core.central_pedidos.ui_streamlit import render_central_pedidos" in harness
    assert "import app" not in harness
    assert 'FM_AI_TEST_MODE") != "1"' in harness
    assert "banco_erp_local.db" in harness
    assert ".tmp" in harness and "fm-ai-playwright" in harness
    assert "app_order_center.py" in launcher
    assert "shell: false" in launcher
    assert "start-order-center-streamlit.cjs" in config
    assert "warmup" not in config
