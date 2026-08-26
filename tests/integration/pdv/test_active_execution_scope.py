from datetime import datetime, timezone

from sqlalchemy import select

from core.pdv.configuracao import carregar_rollout_ambiente
from core.pdv.contexto import contexto_caixa_pdv_autenticado
from core.pdv.roteamento import ModoPDV
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel

from .conftest import InsumoTeste, VendaTeste
from .helpers import executar


def test_active_scope_governa_mapping_venda_e_estoque_com_rollout_divergente(
    fabrica,
    entrada,
    monkeypatch,
) -> None:
    identidade = IdentidadeUsuario(
        usuario_id="operador-multiunidade",
        email="operador-multiunidade@example.com",
        senha_hash="hash-de-teste",
        tenant_id="tenant-teste",
        unidade_id="unidade-padrao",
        papeis=frozenset({Papel.CAIXA}),
        unidades_permitidas=frozenset({"unidade-padrao", "unidade-teste"}),
    ).no_escopo_ativo(
        tenant_id="tenant-teste",
        unidade_id="unidade-teste",
    )
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_TEST_TENANT", "tenant-divergente")
    monkeypatch.setenv("FM_AI_TEST_UNIDADE", "unidade-divergente")
    rollout = carregar_rollout_ambiente()
    contexto = contexto_caixa_pdv_autenticado(
        identidade=identidade,
        usuario_id="caixa-e2e",
        correlation_id="corr-pdv-active-scope",
        instante=datetime.now(timezone.utc),
        origem="test",
    )

    assert (rollout.tenant_id, rollout.unidade_id) != (
        contexto.tenant_id,
        contexto.unidade_id,
    )
    resultado = executar(fabrica, contexto, entrada, ModoPDV.LEGACY)

    assert resultado.sucesso
    with fabrica() as session:
        vendas = session.scalars(select(VendaTeste)).all()
        insumo = session.get(InsumoTeste, 1)
        assert len(vendas) == 1
        assert vendas[0].produto_id == 1
        assert insumo is not None
        assert insumo.saldo_atual == 9
