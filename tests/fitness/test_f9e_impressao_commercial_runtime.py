from pathlib import Path


def test_kds_comercial_compoe_integracao_real_de_impressao() -> None:
    composicao = Path("application/impressao_composicao.py").read_text(encoding="utf-8")
    roteamento = Path("core/kds/ui_roteamento.py").read_text(encoding="utf-8")

    assert "ImpressoraTCPRaw" in composicao
    assert "ResolverDestinosImpressaoSQLAlchemy" in composicao
    assert "impressao_v1_enabled" in composicao
    assert "ImpressoraFake" not in composicao
    assert "runtime_teste" not in composicao

    assert "montar_integracao_impressao_kds" in roteamento
    assert "integracao_impressao=integracao_impressao" in roteamento
