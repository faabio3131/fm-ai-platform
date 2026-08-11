from pathlib import Path

from core.gerente_ia.modelos import ToolGerenteIA


FORBIDDEN = (
    "sqlalchemy",
    "from core.models",
    "import core.models",
    "session.query",
    "execute(text(",
    "client_secret",
    "api_key",
    "authorization =",
)


def test_gerente_ia_nao_importa_orm_sql_ou_segredos() -> None:
    arquivos = list(Path("core/gerente_ia").glob("*.py")) + [Path("core/gerente_ai.py")]
    assert arquivos
    for arquivo in arquivos:
        texto = arquivo.read_text(encoding="utf-8").lower()
        for proibido in FORBIDDEN:
            assert proibido not in texto, f"{arquivo} contém acesso proibido: {proibido}"


def test_v1_nao_expoe_publicacao_campanha_compra_ou_caixa_por_tool() -> None:
    nomes = {tool.value for tool in ToolGerenteIA}
    assert "publicar_campanha" not in nomes
    assert "aprovar_compra" not in nomes
    assert "executar_compra" not in nomes
    assert "confirmar_pagamento" not in nomes
    assert "fechar_caixa" not in nomes
    assert "cancelar_pedido" not in nomes
    assert "concluir_pedido" not in nomes


def test_compra_v1_e_somente_sugestao() -> None:
    nomes = {tool.value for tool in ToolGerenteIA}
    assert "sugerir_compra" in nomes
    assert all("comprar" not in nome for nome in nomes)
