from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from types import SimpleNamespace

from pdv_utils import (
    DINHEIRO_ESPECIE,
    calcular_troco,
    deve_exibir_troco,
    montar_url_qrcode_pix,
    pagamento_dinheiro_suficiente,
    valor_faltante_pagamento,
    FORMAS_PAGAMENTO_PERMITIDAS,
    deve_exibir_valor_recebido,
    formatar_moeda_br,
    validar_estoque_suficiente,
    validar_finalizacao_pdv,
)


def test_qrcode_url_is_plain_https_and_not_markdown():
    url = montar_url_qrcode_pix("FMFIFOOD_PIX_SIMULADO_R$ 79.80 chave pix")
    assert url.startswith("https://")
    assert "[https://" not in url
    assert "](" not in url


def test_qrcode_data_parameter_is_encoded_and_round_trips_symbols():
    payload = "FMFIFOOD_PIX_SIMULADO_R$ 79.80 chave pix + ***"
    url = montar_url_qrcode_pix(payload)
    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert " " not in parsed.query
    assert "R$" not in parsed.query
    assert parse_qs(parsed.query)["data"] == [payload]


def test_qrcode_render_failure_can_be_handled_without_external_request(monkeypatch):
    def fake_image(*_args, **_kwargs):
        raise RuntimeError("media storage failed")

    warnings = []

    class FakeStreamlit:
        image = staticmethod(fake_image)
        warning = staticmethod(lambda message: warnings.append(message))

    try:
        FakeStreamlit.image(montar_url_qrcode_pix("payload"), width=180)
    except Exception:
        FakeStreamlit.warning("Não foi possível exibir o QR Code Pix agora.")

    assert warnings == ["Não foi possível exibir o QR Code Pix agora."]


@pytest.mark.parametrize(
    ("total", "recebido", "troco"),
    [(79.80, 100.00, Decimal("20.20")), (79.80, 79.80, Decimal("0.00")), (0.1 + 0.2, 0.5, Decimal("0.20"))],
)
def test_calcular_troco_com_duas_casas_sem_erro_visivel(total, recebido, troco):
    assert calcular_troco(total, recebido) == troco


def test_pagamento_insuficiente_bloqueia_finalizacao_sem_mutacoes():
    venda_gravada = False
    estoque_baixado = False
    cashback_alterado = False

    assert not pagamento_dinheiro_suficiente(79.80, 50.00)
    assert valor_faltante_pagamento(79.80, 50.00) == Decimal("29.80")
    if pagamento_dinheiro_suficiente(79.80, 50.00):
        venda_gravada = True
        estoque_baixado = True
        cashback_alterado = True

    assert venda_gravada is False
    assert estoque_baixado is False
    assert cashback_alterado is False


def test_pix_e_cartao_nao_exibem_troco_e_dinheiro_exibe():
    assert deve_exibir_troco(DINHEIRO_ESPECIE) is True
    assert deve_exibir_troco("Pix (Gerar QR Code Instantâneo)") is False
    assert deve_exibir_troco("Cartão de Crédito") is False
    assert deve_exibir_troco("Cartão de Débito") is False


def test_valor_total_da_venda_continua_total_liquido_nao_recebido():
    total_final_pdv = 79.80
    valor_recebido = 100.00
    valor_total_venda = total_final_pdv
    assert calcular_troco(total_final_pdv, valor_recebido) == Decimal("20.20")
    assert valor_total_venda == 79.80


def test_app_nao_usa_markdown_em_st_image_do_qrcode_pix():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "st.image(f\"[https://api.qrserver.com" not in source
    assert "montar_url_qrcode_pix(payload_pix)" in source


def produto(**kwargs):
    base = {"id": 1, "preco_venda": 10.0}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_validacao_produto_ausente_sem_gravacao():
    assert validar_finalizacao_pdv(produto=None, quantidade=1, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=10).codigo == "produto_ausente"


def test_validacao_produto_sem_id():
    assert validar_finalizacao_pdv(produto=produto(id=None), quantidade=1, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=10).codigo == "produto_sem_id"


@pytest.mark.parametrize("preco", ["abc", float("nan"), -1])
def test_validacao_preco_invalido(preco):
    assert not validar_finalizacao_pdv(produto=produto(preco_venda=preco), quantidade=1, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=10).valido


@pytest.mark.parametrize("quantidade", [0, -1])
def test_validacao_quantidade_zero_ou_negativa(quantidade):
    assert validar_finalizacao_pdv(produto=produto(), quantidade=quantidade, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=10).codigo == "quantidade_invalida"


@pytest.mark.parametrize("quantidade", [1.5, "2", float("nan")])
def test_validacao_quantidade_nao_inteira(quantidade):
    assert validar_finalizacao_pdv(produto=produto(), quantidade=quantidade, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=10).codigo == "quantidade_nao_inteira"


def test_validacao_forma_pagamento_invalida():
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento="Cheque", valor_recebido=10).codigo == "forma_pagamento_invalida"


def test_dinheiro_sem_valor_recebido():
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=None).codigo == "dinheiro_sem_valor"


def test_dinheiro_negativo():
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=-1).codigo == "dinheiro_negativo"


def test_dinheiro_insuficiente_preserva_pedido():
    resultado = validar_finalizacao_pdv(produto=produto(), quantidade=3, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=20)
    assert resultado.codigo == "dinheiro_insuficiente"
    assert "R$ 10,00" in resultado.mensagem


def test_dinheiro_exato_e_com_troco():
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=10).troco == Decimal("0.00")
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento=DINHEIRO_ESPECIE, valor_recebido=20).troco == Decimal("10.00")


def test_pix_e_cartao_sem_valor_recebido_ou_troco():
    for forma in FORMAS_PAGAMENTO_PERMITIDAS:
        if forma != DINHEIRO_ESPECIE:
            resultado = validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento=forma)
            assert resultado.valido
            assert not deve_exibir_valor_recebido(forma)
            assert not deve_exibir_troco(forma)


def test_cliente_ausente_permitido_e_cliente_invalido_bloqueado():
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento="Cartão de Débito", cliente_selecionado=None).valido
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento="Cartão de Débito", cliente_selecionado=SimpleNamespace(id=7), cliente_existe=False).codigo == "cliente_invalido"


def test_estoque_suficiente_e_insuficiente_sem_baixa_parcial():
    ficha = SimpleNamespace(insumo_id=1, quantidade_utilizada=2)
    insumo = SimpleNamespace(nome="Hambúrguer 120g", saldo_atual=3)
    assert validar_estoque_suficiente([ficha], {1: insumo}, 1).valido
    resultado = validar_estoque_suficiente([ficha], {1: insumo}, 2)
    assert resultado.codigo == "estoque_insuficiente"
    assert insumo.saldo_atual == 3


def test_cashback_nao_alterado_em_falha_e_total_zero_permitido():
    saldo = Decimal("10.00")
    falha = validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento="Cartão de Débito", usar_cashback=True, desconto_cashback=11)
    assert falha.codigo == "cashback_maior_que_total"
    assert saldo == Decimal("10.00")
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento="Cartão de Débito", usar_cashback=True, desconto_cashback=10).total_final == Decimal("0.00")


def test_formata_moeda_brasileira():
    assert formatar_moeda_br(127.6) == "R$ 127,60"
    assert formatar_moeda_br(150) == "R$ 150,00"
    assert formatar_moeda_br(1222.4) == "R$ 1.222,40"


def test_pix_producao_exige_confirmacao_valida():
    assert validar_finalizacao_pdv(produto=produto(), quantidade=1, forma_pagamento="Pix (Gerar QR Code Instantâneo)", pix_producao=True, pix_confirmado=False).codigo == "pix_sem_confirmacao"
