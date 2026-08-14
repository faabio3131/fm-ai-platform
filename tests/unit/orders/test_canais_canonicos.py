from core.dominio.enums import CanalAtendimento, OrigemPedido


def test_origens_canonicas_separam_canais_financeiros_e_operacionais() -> None:
    esperadas = {
        "PDV": "pdv",
        "SALAO": "salao",
        "DELIVERY_PROPRIO": "delivery_proprio",
        "IFOOD": "ifood",
        "FOOD99": "food99",
        "KEETA": "keeta",
        "WHATSAPP": "whatsapp",
        "MICA": "mica",
    }
    for nome, valor in esperadas.items():
        assert getattr(OrigemPedido, nome).value == valor
        assert getattr(CanalAtendimento, nome).value == valor


def test_valores_legados_continuam_validos_para_cutover_gradual() -> None:
    assert OrigemPedido("balcao") is OrigemPedido.BALCAO
    assert OrigemPedido("marketplace") is OrigemPedido.MARKETPLACE
    assert CanalAtendimento("presencial") is CanalAtendimento.PRESENCIAL
    assert CanalAtendimento("marketplace") is CanalAtendimento.MARKETPLACE
