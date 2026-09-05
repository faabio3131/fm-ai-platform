from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_adapter_comercial_e_real_sem_fake() -> None:
    text = _text("infra/impressao/adapter_tcp.py")
    assert "class ImpressoraTCPRaw" in text
    assert "socket.create_connection" in text
    assert "ImpressoraFake" not in text
    assert "runtime_teste" not in text


def test_configuracao_duravel_reutiliza_admin_existente() -> None:
    text = _text("infra/impressao/configuracao_sqlalchemy.py")
    assert "RepositorioAdministracaoSQLAlchemy" in text
    assert "parametros_operacionais" in text
    assert "DestinoImpressao" in text
    assert "tenant_id" in text and "unidade_id" in text and "setor_id" in text


def test_superficie_comercial_exposta_no_app() -> None:
    app = _text("app.py")
    ui = _text("core/impressao/ui_comercial.py")
    assert "render_impressao_operacional" in app
    assert "Impressão Operacional" in app
    assert "reimprimir" in ui
    assert "ImpressoraFake" not in ui
