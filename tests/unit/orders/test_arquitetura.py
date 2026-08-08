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
