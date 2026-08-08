from sqlalchemy import func, select

from core.pdv.roteamento import ModoPDV

from .conftest import ClienteTeste, InsumoTeste, VendaTeste
from .helpers import executar


def test_legacy_integrado_preserva_um_commit_e_um_efeito(fabrica, contexto, entrada):
    resultado = executar(fabrica, contexto, entrada, ModoPDV.LEGACY)
    assert resultado.sucesso
    with fabrica() as session:
        assert session.scalar(select(func.count()).select_from(VendaTeste)) == 1
        assert session.get(InsumoTeste, 1).saldo_atual == 9
        assert session.get(ClienteTeste, 1).saldo_cashback == 6.25
