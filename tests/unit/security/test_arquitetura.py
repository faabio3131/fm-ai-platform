from pathlib import Path


def test_seguranca_nao_depende_de_ui_orm_ia_ou_sessao():
    textos = "\n".join(
        p.read_text(encoding="utf-8").lower()
        for p in Path("core/seguranca").glob("*.py")
    )
    for proibido in (
        "streamlit",
        "sqlalchemy",
        "import app",
        "gemini",
        "session_state",
        "core.database",
    ):
        assert proibido not in textos


def test_app_ainda_nao_importa_nova_seguranca():
    assert "core.seguranca" not in Path("app.py").read_text(encoding="utf-8")
