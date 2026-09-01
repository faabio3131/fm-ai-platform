from scripts.mercado_pago_access_token_identidade import identificar_token


def test_identificar_token_expoe_somente_client_id_publico() -> None:
    resultado = identificar_token("APP_USR-5746890230579422-081923-acde1234")

    assert resultado == {
        "prefixo": "APP_USR",
        "client_id": "5746890230579422",
        "formato_reconhecido": True,
    }
    assert "081923" not in repr(resultado)
    assert "acde1234" not in repr(resultado)


def test_identificar_token_nao_expoe_formato_desconhecido() -> None:
    resultado = identificar_token("segredo-sem-formato-publico")

    assert resultado == {
        "prefixo": "desconhecido",
        "client_id": None,
        "formato_reconhecido": False,
    }
    assert "segredo" not in repr(resultado)
