import pytest

from core.delivery.alcance_rota import AlcanceEntrega
from core.delivery.erros import ErroDelivery


@pytest.mark.parametrize("distancia", [0, 8000, 10000])
def test_percurso_dentro_do_limite(distancia):
    AlcanceEntrega("tenant", "unidade", 10).validar_rota(distancia)


@pytest.mark.parametrize("distancia", [10001, 12700])
def test_percurso_fora_do_limite(distancia):
    with pytest.raises(ErroDelivery, match="fora_do_alcance_entrega"):
        AlcanceEntrega("tenant", "unidade", 10).validar_rota(distancia)


@pytest.mark.parametrize("distancia", [None, -1])
def test_falha_exige_gestor_e_entregador_sem_aprovacao_automatica(distancia):
    with pytest.raises(ErroDelivery, match="rota_indisponivel_exige_gestor_entregador"):
        AlcanceEntrega("tenant", "unidade", 10).validar_rota(distancia)


@pytest.mark.parametrize("limite", [0, 201])
def test_limite_invalido(limite):
    with pytest.raises(ErroDelivery, match="alcance_entrega_invalido"):
        AlcanceEntrega("tenant", "unidade", limite)
