from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.central_pedidos.alertas import ConfiguracaoAlertas, calcular_alertas
from core.central_pedidos.flags import order_center_v1_enabled
from core.central_pedidos.modelos import FiltroCentralPedidos, ResumoFinanceiroCentral


def financeiro(situacao="pendente", reconciliacao=None):
    return ResumoFinanceiroCentral(
        situacao, Decimal("10.00"), Decimal("0.00"), reconciliacao_status=reconciliacao
    )


def test_filtros_validam_paginacao_utc_e_busca():
    assert FiltroCentralPedidos(busca=" ped ").busca == "ped"
    with pytest.raises(ValueError):
        FiltroCentralPedidos(pagina=0)
    with pytest.raises(ValueError):
        FiltroCentralPedidos(criado_de=datetime.now())


def test_alertas_sao_deterministas_configuraveis_e_utc():
    agora = datetime(2026, 8, 8, 12, tzinfo=timezone.utc)
    alertas = calcular_alertas(
        status="confirmado",
        atualizado_em=agora - timedelta(minutes=31),
        financeiro=financeiro(reconciliacao="divergente"),
        agora=agora,
        configuracao=ConfiguracaoAlertas(timedelta(minutes=30)),
    )
    assert [a.tipo for a in alertas] == [
        "PAGAMENTO_PENDENTE",
        "RECONCILIACAO_DIVERGENTE",
        "PEDIDO_SEM_ATUALIZACAO",
    ]


def test_flag_e_somente_server_side_em_teste(monkeypatch):
    monkeypatch.setenv("FM_AI_ORDER_CENTER_V1", "1")
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    assert not order_center_v1_enabled()
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    assert order_center_v1_enabled()
