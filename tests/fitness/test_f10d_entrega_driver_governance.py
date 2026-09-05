from __future__ import annotations

import inspect

from application import entrega_composicao, entrega_transacoes
from core.entrega import ui_streamlit


def test_commercial_ui_uses_canonical_driver_governance() -> None:
    source = inspect.getsource(ui_streamlit._acoes_expedicao)
    test_guard = source.index('os.getenv("FM_AI_TEST_MODE") == "1"')
    free_id = source.index("st.text_input(")
    governed = source.index("listar_entregadores_elegiveis")
    governed_write = source.index("atribuir_entregador_governado")

    assert test_guard < free_id < governed < governed_write
    assert "st.selectbox(" in source


def test_governed_assignment_revalidates_identity_before_write_and_commit() -> None:
    source = inspect.getsource(
        entrega_transacoes.AplicacaoEntregaV1.atribuir_entregador_governado
    )
    assert source.index("validar_entregador_elegivel") < source.index(".atribuir(")
    assert source.index(".atribuir(") < source.index("uow.commit()")


def test_driver_eligibility_requires_active_tenant_role_and_unit() -> None:
    source = inspect.getsource(entrega_composicao._elegivel)
    assert "identidade.ativo" in source
    assert "identidade.tenant_id == contexto.tenant_id" in source
    assert "Papel.ENTREGADOR in identidade.papeis" in source
    assert "contexto.unidade_id in identidade.unidades_permitidas" in source
