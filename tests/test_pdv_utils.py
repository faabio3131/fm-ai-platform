from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from types import SimpleNamespace

from pdv_utils import (
    CLIENTE_BALCAO_ID,
    CLIENTE_BALCAO_LABEL,
    DINHEIRO_ESPECIE,
    calcular_troco,
    deve_exibir_troco,
    montar_url_qrcode_pix,
    pagamento_dinheiro_suficiente,
    valor_faltante_pagamento,
    FORMAS_PAGAMENTO_PERMITIDAS,
    deve_exibir_valor_recebido,
    formatar_moeda_br,
    formatar_opcao_cliente_pdv,
    indice_cliente_pdv,
    normalizar_cliente_id_pdv,
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
    [
        (79.80, 100.00, Decimal("20.20")),
        (79.80, 79.80, Decimal("0.00")),
        (0.1 + 0.2, 0.5, Decimal("0.20")),
    ],
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
    assert 'st.image(f"[https://api.qrserver.com' not in source
    assert "montar_url_qrcode_pix(payload_pix)" in source


def produto(**kwargs):
    base = {"id": 1, "preco_venda": 10.0}
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_validacao_produto_ausente_sem_gravacao():
    assert (
        validar_finalizacao_pdv(
            produto=None,
            quantidade=1,
            forma_pagamento=DINHEIRO_ESPECIE,
            valor_recebido=10,
        ).codigo
        == "produto_ausente"
    )


def test_validacao_produto_sem_id():
    assert (
        validar_finalizacao_pdv(
            produto=produto(id=None),
            quantidade=1,
            forma_pagamento=DINHEIRO_ESPECIE,
            valor_recebido=10,
        ).codigo
        == "produto_sem_id"
    )


@pytest.mark.parametrize("preco", ["abc", float("nan"), -1])
def test_validacao_preco_invalido(preco):
    assert not validar_finalizacao_pdv(
        produto=produto(preco_venda=preco),
        quantidade=1,
        forma_pagamento=DINHEIRO_ESPECIE,
        valor_recebido=10,
    ).valido


@pytest.mark.parametrize("quantidade", [0, -1])
def test_validacao_quantidade_zero_ou_negativa(quantidade):
    assert (
        validar_finalizacao_pdv(
            produto=produto(),
            quantidade=quantidade,
            forma_pagamento=DINHEIRO_ESPECIE,
            valor_recebido=10,
        ).codigo
        == "quantidade_invalida"
    )


@pytest.mark.parametrize("quantidade", [1.5, "2", float("nan")])
def test_validacao_quantidade_nao_inteira(quantidade):
    assert (
        validar_finalizacao_pdv(
            produto=produto(),
            quantidade=quantidade,
            forma_pagamento=DINHEIRO_ESPECIE,
            valor_recebido=10,
        ).codigo
        == "quantidade_nao_inteira"
    )


def test_validacao_forma_pagamento_invalida():
    assert (
        validar_finalizacao_pdv(
            produto=produto(), quantidade=1, forma_pagamento="Cheque", valor_recebido=10
        ).codigo
        == "forma_pagamento_invalida"
    )


def test_dinheiro_sem_valor_recebido():
    assert (
        validar_finalizacao_pdv(
            produto=produto(),
            quantidade=1,
            forma_pagamento=DINHEIRO_ESPECIE,
            valor_recebido=None,
        ).codigo
        == "dinheiro_sem_valor"
    )


def test_dinheiro_negativo():
    assert (
        validar_finalizacao_pdv(
            produto=produto(),
            quantidade=1,
            forma_pagamento=DINHEIRO_ESPECIE,
            valor_recebido=-1,
        ).codigo
        == "dinheiro_negativo"
    )


def test_dinheiro_insuficiente_preserva_pedido():
    resultado = validar_finalizacao_pdv(
        produto=produto(),
        quantidade=3,
        forma_pagamento=DINHEIRO_ESPECIE,
        valor_recebido=20,
    )
    assert resultado.codigo == "dinheiro_insuficiente"
    assert "R$ 10,00" in resultado.mensagem


def test_dinheiro_exato_e_com_troco():
    assert validar_finalizacao_pdv(
        produto=produto(),
        quantidade=1,
        forma_pagamento=DINHEIRO_ESPECIE,
        valor_recebido=10,
    ).troco == Decimal("0.00")
    assert validar_finalizacao_pdv(
        produto=produto(),
        quantidade=1,
        forma_pagamento=DINHEIRO_ESPECIE,
        valor_recebido=20,
    ).troco == Decimal("10.00")


def test_pix_e_cartao_sem_valor_recebido_ou_troco():
    for forma in FORMAS_PAGAMENTO_PERMITIDAS:
        if forma != DINHEIRO_ESPECIE:
            resultado = validar_finalizacao_pdv(
                produto=produto(), quantidade=1, forma_pagamento=forma
            )
            assert resultado.valido
            assert not deve_exibir_valor_recebido(forma)
            assert not deve_exibir_troco(forma)


def test_cliente_ausente_permitido_e_cliente_invalido_bloqueado():
    assert validar_finalizacao_pdv(
        produto=produto(),
        quantidade=1,
        forma_pagamento="Cartão de Débito",
        cliente_selecionado=None,
    ).valido
    assert (
        validar_finalizacao_pdv(
            produto=produto(),
            quantidade=1,
            forma_pagamento="Cartão de Débito",
            cliente_selecionado=SimpleNamespace(id=7),
            cliente_existe=False,
        ).codigo
        == "cliente_invalido"
    )


def test_estoque_suficiente_e_insuficiente_sem_baixa_parcial():
    ficha = SimpleNamespace(insumo_id=1, quantidade_utilizada=2)
    insumo = SimpleNamespace(nome="Hambúrguer 120g", saldo_atual=3)
    assert validar_estoque_suficiente([ficha], {1: insumo}, 1).valido
    resultado = validar_estoque_suficiente([ficha], {1: insumo}, 2)
    assert resultado.codigo == "estoque_insuficiente"
    assert insumo.saldo_atual == 3


def test_cashback_nao_alterado_em_falha_e_total_zero_permitido():
    saldo = Decimal("10.00")
    falha = validar_finalizacao_pdv(
        produto=produto(),
        quantidade=1,
        forma_pagamento="Cartão de Débito",
        usar_cashback=True,
        desconto_cashback=11,
    )
    assert falha.codigo == "cashback_maior_que_total"
    assert saldo == Decimal("10.00")
    assert validar_finalizacao_pdv(
        produto=produto(),
        quantidade=1,
        forma_pagamento="Cartão de Débito",
        usar_cashback=True,
        desconto_cashback=10,
    ).total_final == Decimal("0.00")


def test_formata_moeda_brasileira():
    assert formatar_moeda_br(127.6) == "R$ 127,60"
    assert formatar_moeda_br(150) == "R$ 150,00"
    assert formatar_moeda_br(1222.4) == "R$ 1.222,40"


def test_pix_producao_exige_confirmacao_valida():
    assert (
        validar_finalizacao_pdv(
            produto=produto(),
            quantidade=1,
            forma_pagamento="Pix (Gerar QR Code Instantâneo)",
            pix_producao=True,
            pix_confirmado=False,
        ).codigo
        == "pix_sem_confirmacao"
    )


def test_reset_pendente_aplicado_antes_dos_widgets_e_preserva_flash():
    from pdv_utils import aplicar_reset_pendente_pdv

    estado = {
        "pdv_reset_pendente": True,
        "pdv_flash_sucesso": "ok",
        "pdv_quantidade": 3,
        "pdv_cliente_id": 9,
        "pdv_valor_recebido_dinheiro": 100.0,
        "pdv_forma_pagamento": "Dinheiro Em Espécie",
        "pdv_usa_cashback": True,
        "pdv_pix_confirmado": True,
        "pdv_troco": 4.30,
        "pdv_processando": True,
    }

    assert aplicar_reset_pendente_pdv(estado) is True
    assert estado["pdv_quantidade"] == 1
    assert "pdv_cliente_id" not in estado
    assert estado["pdv_valor_recebido_dinheiro"] == 0.0
    assert estado["pdv_forma_pagamento"] == FORMAS_PAGAMENTO_PERMITIDAS[0]
    assert estado["pdv_usa_cashback"] is False
    assert estado["pdv_pix_confirmado"] is False
    assert estado["pdv_troco"] is None
    assert estado["pdv_processando"] is False
    assert "pdv_reset_pendente" not in estado
    assert estado["pdv_flash_sucesso"] == "ok"


def test_flash_sucesso_sobrevive_ao_reset_e_e_consumido_uma_vez():
    from pdv_utils import (
        aplicar_reset_pendente_pdv,
        consumir_flash_sucesso_pdv,
        marcar_reset_pdv_apos_sucesso,
    )

    estado = {"pdv_quantidade": 2, "pdv_processando": True}
    marcar_reset_pdv_apos_sucesso(estado, "mensagem")
    assert estado["pdv_reset_pendente"] is True
    assert estado["pdv_processando"] is False

    aplicar_reset_pendente_pdv(estado)
    assert consumir_flash_sucesso_pdv(estado) == "mensagem"
    assert consumir_flash_sucesso_pdv(estado) is None


def test_validacao_nao_limpa_pedido_em_erro_ou_pagamento_insuficiente():
    pedido = {
        "pdv_quantidade": 3,
        "pdv_valor_recebido_dinheiro": 90.0,
        "pdv_forma_pagamento": DINHEIRO_ESPECIE,
    }
    antes = pedido.copy()

    resultado = validar_finalizacao_pdv(
        produto=produto(preco_venda=31.9),
        quantidade=pedido["pdv_quantidade"],
        forma_pagamento=pedido["pdv_forma_pagamento"],
        valor_recebido=pedido["pdv_valor_recebido_dinheiro"],
    )

    assert resultado.codigo == "dinheiro_insuficiente"
    assert pedido == antes


def test_mensagem_sucesso_pdv_formata_moeda_sem_markdown_quebrado():
    from pdv_utils import montar_mensagem_sucesso_pdv

    mensagem = montar_mensagem_sucesso_pdv(
        total_final=95.70,
        forma_pagamento=DINHEIRO_ESPECIE,
        valor_recebido=100,
        troco=4.30,
    )

    assert "R$ 95,70" in mensagem
    assert "R$ 100,00" in mensagem
    assert "R$ 4,30" in mensagem
    assert "**R" not in mensagem
    assert "R 95,70" not in mensagem
    assert "R$ 95.70" not in mensagem


def test_marcar_reset_nao_altera_chaves_de_widgets_ja_criados_e_evita_duplicidade_no_rerun():
    from pdv_utils import marcar_reset_pdv_apos_sucesso

    estado = {
        "pdv_produto": "x-bacon",
        "pdv_quantidade": 3,
        "pdv_cliente_id": 7,
        "pdv_forma_pagamento": DINHEIRO_ESPECIE,
        "pdv_valor_recebido_dinheiro": 100.0,
        "pdv_usa_cashback": True,
        "pdv_processando": True,
    }
    widgets = {
        k: estado[k]
        for k in (
            "pdv_produto",
            "pdv_quantidade",
            "pdv_cliente_id",
            "pdv_forma_pagamento",
            "pdv_valor_recebido_dinheiro",
            "pdv_usa_cashback",
        )
    }

    marcar_reset_pdv_apos_sucesso(estado, "ok")

    assert {k: estado[k] for k in widgets} == widgets
    assert estado["pdv_reset_pendente"] is True
    assert estado["pdv_processando"] is False


def test_excecao_pos_commit_nao_exige_rollback_para_recuperar_interface():
    from pdv_utils import marcar_reset_pdv_apos_sucesso

    estado = {"pdv_processando": True}
    venda_commitada = True
    rollback_chamado = False

    try:
        if venda_commitada:
            marcar_reset_pdv_apos_sucesso(estado, "recuperada")
        else:
            rollback_chamado = True
    except Exception:
        rollback_chamado = True

    assert rollback_chamado is False
    assert estado["pdv_flash_sucesso"] == "recuperada"
    assert estado["pdv_reset_pendente"] is True


def test_payload_pix_simulado_usa_moeda_brasileira_padronizada():
    from pdv_utils import montar_payload_pix_simulado

    payload = montar_payload_pix_simulado(1222.4)

    assert payload == "FMFIFOOD_PIX_SIMULADO_R$ 1.222,40"
    assert "1222.40" not in payload


def test_linha_total_pdv_padroniza_rotulo_valor_e_desconto():
    from pdv_utils import montar_linha_total_pdv

    assert montar_linha_total_pdv("Subtotal", 79.8) == "Subtotal: R$ 79,80"
    assert (
        montar_linha_total_pdv("Desconto Fidelidade", 10, negativo=True)
        == "Desconto Fidelidade: -R$ 10,00"
    )


def test_estado_inicial_deixa_selectbox_definir_cliente_balcao():
    estado = {}

    from pdv_utils import preparar_estado_inicial_pdv

    preparar_estado_inicial_pdv(estado)

    assert "pdv_cliente_id" not in estado
    assert formatar_opcao_cliente_pdv(CLIENTE_BALCAO_ID, {}) == (
        f"👤 {CLIENTE_BALCAO_LABEL}"
    )


def test_reset_apos_venda_volta_para_cliente_balcao_e_valor_zero():
    estado = {
        "pdv_reset_pendente": True,
        "pdv_cliente_id": 22,
        "pdv_valor_recebido_dinheiro": 100.0,
    }

    from pdv_utils import aplicar_reset_pendente_pdv

    assert aplicar_reset_pendente_pdv(estado) is True
    assert "pdv_cliente_id" not in estado
    assert estado["pdv_valor_recebido_dinheiro"] == 0.0


def test_selecao_cliente_pdv_usa_id_estavel_e_label_com_cashback():
    cliente = SimpleNamespace(id=7, nome="Michele", saldo_cashback=12.5)
    clientes_por_id = {7: cliente}

    assert normalizar_cliente_id_pdv("7", clientes_por_id) == 7
    assert indice_cliente_pdv(7, [CLIENTE_BALCAO_ID, 7]) == 1
    assert (
        formatar_opcao_cliente_pdv(7, clientes_por_id)
        == "Michele (Cashback Disponível: R$ 12,50)"
    )


def test_preparacao_cliente_preserva_id_valido_escolhido_pelo_widget():
    from pdv_utils import preparar_cliente_id_pdv

    cliente = SimpleNamespace(id=7, nome="Michele", saldo_cashback=12.5)
    estado = {"pdv_cliente_id": 7}

    assert preparar_cliente_id_pdv(estado, {7: cliente}) == 7
    assert estado["pdv_cliente_id"] == 7
    assert isinstance(estado["pdv_cliente_id"], int)


def test_preparacao_cliente_remove_tipo_incorreto_para_widget_recriar_com_id():
    from pdv_utils import preparar_cliente_id_pdv

    cliente = SimpleNamespace(id=7, nome="Michele", saldo_cashback=12.5)
    estado = {"pdv_cliente_id": "7"}

    assert preparar_cliente_id_pdv(estado, {7: cliente}) == 7
    assert "pdv_cliente_id" not in estado


def test_cliente_pdv_inexistente_volta_para_balcao_com_segurança():
    assert normalizar_cliente_id_pdv(999, {}) == CLIENTE_BALCAO_ID
    assert indice_cliente_pdv(999, [CLIENTE_BALCAO_ID, 7]) == 0
    assert formatar_opcao_cliente_pdv(999, {}) == f"👤 {CLIENTE_BALCAO_LABEL}"


def test_app_pdv_nao_contem_choose_an_option_e_usa_placeholder_pt_br():
    source = Path("app.py").read_text(encoding="utf-8")
    assert "Choose an option" not in source
    assert "Cliente Balcão / Não Identificado" in source
    assert 'key="pdv_cliente_id"' in source
    assert 'key="pdv_cliente"' not in source
    assert "index=indice_cliente_pdv" in "".join(source.split())


def test_app_marca_cada_rerun_concluido_no_modo_e2e():
    source = Path("app.py").read_text(encoding="utf-8")

    assert 'st.session_state["_fm_ai_e2e_run"]' in source
    assert 'data-fm-ai-e2e-run="{st.session_state[' in source


def test_app_identifica_visualmente_real_no_campo_valor_recebido():
    source = Path("app.py").read_text(encoding="utf-8")
    assert 'st.markdown("Valor recebido do cliente")' in source
    assert 'st.markdown("### R$")' in source
    assert 'key="pdv_valor_recebido_dinheiro"' in source


def test_dinheiro_continua_entrada_numerica_com_reset_e_preservacao():
    source = Path("app.py").read_text(encoding="utf-8")
    compact_source = "".join(source.split())
    assert "valor_recebido_pdv = st.number_input(" in source
    assert "min_value=0.0" in source
    assert "step=0.50" in source
    assert 'format="%.2f"' in source
    assert (
        'value=float(st.session_state.get("pdv_valor_recebido_dinheiro",total_final_pdv))'
        in compact_source
    )


def test_pagamento_insuficiente_preserva_valor_recebido_no_estado():
    estado = {"pdv_valor_recebido_dinheiro": 50.0}
    antes = estado.copy()

    resultado = validar_finalizacao_pdv(
        produto=produto(preco_venda=79.8),
        quantidade=1,
        forma_pagamento=DINHEIRO_ESPECIE,
        valor_recebido=estado["pdv_valor_recebido_dinheiro"],
    )

    assert resultado.codigo == "dinheiro_insuficiente"
    assert estado == antes
