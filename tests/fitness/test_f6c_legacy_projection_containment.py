from pathlib import Path

from core.pdv.adaptadores_sqlalchemy import (
    PonteProjecaoCompatLegadaPDVSQLAlchemy,
)


def test_f6c_ponte_canonica_nao_expoe_execucao_ou_baixa_estoque() -> None:
    assert not hasattr(PonteProjecaoCompatLegadaPDVSQLAlchemy, "executar")
    assert not hasattr(
        PonteProjecaoCompatLegadaPDVSQLAlchemy,
        "baixar_estoque_uma_vez",
    )
    assert hasattr(PonteProjecaoCompatLegadaPDVSQLAlchemy, "validar_estoque")
    assert hasattr(PonteProjecaoCompatLegadaPDVSQLAlchemy, "criar_venda_uma_vez")
    assert hasattr(
        PonteProjecaoCompatLegadaPDVSQLAlchemy,
        "aplicar_cashback_uma_vez",
    )


def test_f6c_projecao_financeira_nao_pode_alterar_estoque_legado() -> None:
    source = Path("application/pdv_legacy_projection.py").read_text(encoding="utf-8")
    assert "projetar_estoque" not in source
    assert "ESTOQUE_LEGADO" not in source
    assert "atualizar_insumo_legado" not in source
    assert "obter_insumo_por_id_legado" not in source


def test_f6c_finalizador_financeiro_nao_consulta_reserva_para_baixa_legada() -> None:
    source = Path("application/finalizacao_pagamento.py").read_text(encoding="utf-8")
    assert "recursos.estoque.buscar_reserva" not in source
    assert "projetar_estoque" not in source


def test_f6c_executor_canonico_recebe_ponte_restrita() -> None:
    executor = Path("core/pdv/executor_canonico.py").read_text(encoding="utf-8")
    app = Path("app.py").read_text(encoding="utf-8")
    assert "legado: PonteProjecaoCompatLegadaPDV" in executor
    assert "baixar_estoque_uma_vez" not in executor
    assert "PonteProjecaoCompatLegadaPDVSQLAlchemy(legado_pdv)" in app
