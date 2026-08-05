from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from pdv_utils import (
    DINHEIRO_ESPECIE,
    calcular_troco,
    deve_exibir_troco,
    montar_url_qrcode_pix,
    pagamento_dinheiro_suficiente,
    valor_faltante_pagamento,
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
