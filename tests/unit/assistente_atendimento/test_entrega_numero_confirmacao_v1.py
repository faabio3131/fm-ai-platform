import pytest

from core.integracoes.google_maps import ErroGoogleMaps
from infra.assistente_atendimento.entrega_maps import _exigir_numero_entrega_confirmado


@pytest.mark.parametrize("endereco", [
    "Rua Coronel Macedo, 53",
    "Rua Coronel Macedo, número 53",
    "Rua Coronel Macedo, nº 53, Paraíso (Polvilho)",
])
def test_numero_geocodificado_coincide_com_informado(endereco):
    _exigir_numero_entrega_confirmado(endereco, "53")


@pytest.mark.parametrize("endereco,numero_maps", [
    ("Rua Coronel Macedo, 53", "35"),
    ("Rua Coronel Macedo, 53", None),
    ("Rua Coronel Macedo, CEP 07794-080", "53"),
    ("Rua Coronel Macedo", "53"),
])
def test_nao_homologa_cotacao_com_numero_ausente_ou_divergente(endereco, numero_maps):
    with pytest.raises(ErroGoogleMaps):
        _exigir_numero_entrega_confirmado(endereco, numero_maps)
