from decimal import Decimal

import pytest

from core.dominio.enums import PagamentoStatus
from core.mica import (
    ErroMica,
    EstadoAtendimentoMica,
    OperacaoMicaFake,
    ProdutoCatalogoMica,
    ServicoMica,
    mica_v1_enabled,
    parse_intencao_mica,
)
from core.pagamentos.modelos import MetodoPagamento


def _catalogo() -> tuple[ProdutoCatalogoMica, ...]:
    return (
        ProdutoCatalogoMica("p1", "tenant-1", "unidade-1", "Burger Teste", Decimal("29.90")),
        ProdutoCatalogoMica("p2", "tenant-1", "unidade-1", "Batata Teste", Decimal("18.50")),
    )


def _raw(nome: str = "Burger Teste", quantidade: int = 1) -> str:
    return (
        '{"cliente_nome":"Cliente Teste","itens":['
        f'{{"nome_produto":"{nome}","quantidade":{quantidade}}}'
        '],"resposta_whatsapp":"Revise seu carrinho antes de confirmar."}'
    )


def _servico(status: PagamentoStatus = PagamentoStatus.PENDENTE):
    operacao = OperacaoMicaFake(status_pagamento=status)
    return ServicoMica(pedidos=operacao, pagamentos=operacao, handoff=operacao), operacao


def test_flag_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FM_AI_TEST_MODE", raising=False)
    monkeypatch.setenv("FM_AI_MICA_V1", "1")
    assert not mica_v1_enabled()
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    assert mica_v1_enabled()


def test_schema_rejeita_markdown_e_campos_extras() -> None:
    with pytest.raises(ErroMica) as exc:
        parse_intencao_mica("```json\n" + _raw() + "\n```")
    assert exc.value.codigo == "schema_mica_invalido"

    bruto = _raw()[:-1] + ',"pagamento":"aprovado"}'
    with pytest.raises(ErroMica) as exc:
        parse_intencao_mica(bruto)
    assert exc.value.codigo == "schema_mica_invalido"


def test_schema_rejeita_quantidade_invalida() -> None:
    with pytest.raises(ErroMica) as exc:
        parse_intencao_mica(_raw(quantidade=0))
    assert exc.value.codigo == "schema_item_mica_invalido"


def test_produto_exato_monta_carrinho_sem_efeitos() -> None:
    servico, operacao = _servico()
    resultado = servico.interpretar(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia=_raw(),
        catalogo=_catalogo(),
    )
    assert resultado.estado is EstadoAtendimentoMica.AGUARDANDO_CONFIRMACAO
    assert resultado.carrinho is not None
    assert resultado.carrinho.total == Decimal("29.90")
    assert operacao.chamadas_pedido == 0
    assert operacao.chamadas_pagamento == 0


def test_nome_parcial_nao_cai_no_primeiro_produto() -> None:
    servico, operacao = _servico()
    resultado = servico.interpretar(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia=_raw(nome="Burger"),
        catalogo=_catalogo(),
    )
    assert resultado.estado is EstadoAtendimentoMica.HANDOFF_HUMANO
    assert resultado.handoff_motivo == "produto_nao_resolvido_exatamente"
    assert operacao.chamadas_pedido == 0


def test_erro_da_ia_nao_inventa_pedido() -> None:
    servico, operacao = _servico()
    resultado = servico.interpretar(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia="{resposta inválida",
        catalogo=_catalogo(),
    )
    assert resultado.estado is EstadoAtendimentoMica.HANDOFF_HUMANO
    assert operacao.chamadas_pedido == 0
    assert operacao.chamadas_pagamento == 0


def test_confirmacao_explicita_e_fingerprint_sao_obrigatorios() -> None:
    servico, _ = _servico()
    analisado = servico.interpretar(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia=_raw(),
        catalogo=_catalogo(),
    )
    assert analisado.carrinho is not None
    with pytest.raises(ErroMica) as exc:
        servico.confirmar(
            resultado=analisado,
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            cliente_ref="cliente-hash",
            confirmacao_cliente=False,
            fingerprint_confirmado=analisado.carrinho.fingerprint,
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirm-1",
        )
    assert exc.value.codigo == "confirmacao_cliente_obrigatoria"

    with pytest.raises(ErroMica) as exc:
        servico.confirmar(
            resultado=analisado,
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            cliente_ref="cliente-hash",
            confirmacao_cliente=True,
            fingerprint_confirmado="fingerprint-antigo",
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirm-1",
        )
    assert exc.value.codigo == "carrinho_alterado_reconfirmacao_obrigatoria"


def test_pagamento_pendente_nunca_e_promovido_a_pago() -> None:
    servico, operacao = _servico(PagamentoStatus.PENDENTE)
    analisado = servico.interpretar(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia=_raw(),
        catalogo=_catalogo(),
    )
    assert analisado.carrinho is not None
    final = servico.confirmar(
        resultado=analisado,
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        cliente_ref="cliente-hash",
        confirmacao_cliente=True,
        fingerprint_confirmado=analisado.carrinho.fingerprint,
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirm-1",
    )
    assert final.estado is EstadoAtendimentoMica.PEDIDO_CONFIRMADO
    assert final.pagamento is not None
    assert final.pagamento.status is PagamentoStatus.PENDENTE
    assert "pendente" in final.mensagem.lower()
    assert operacao.chamadas_pedido == 1
    assert operacao.chamadas_pagamento == 1


def test_pago_so_quando_porta_financeira_informa_pago() -> None:
    servico, _ = _servico(PagamentoStatus.PAGO)
    analisado = servico.interpretar(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia=_raw(),
        catalogo=_catalogo(),
    )
    assert analisado.carrinho is not None
    final = servico.confirmar(
        resultado=analisado,
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        cliente_ref="cliente-hash",
        confirmacao_cliente=True,
        fingerprint_confirmado=analisado.carrinho.fingerprint,
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirm-1",
    )
    assert final.pagamento is not None
    assert final.pagamento.status is PagamentoStatus.PAGO
    assert "fonte financeira autorizada" in final.mensagem


def test_repeticao_de_confirmacao_e_idempotente() -> None:
    servico, operacao = _servico()
    analisado = servico.interpretar(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia=_raw(),
        catalogo=_catalogo(),
    )
    assert analisado.carrinho is not None
    kwargs = dict(
        resultado=analisado,
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        cliente_ref="cliente-hash",
        confirmacao_cliente=True,
        fingerprint_confirmado=analisado.carrinho.fingerprint,
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirm-1",
    )
    primeiro = servico.confirmar(**kwargs)
    repetido = servico.confirmar(**kwargs)
    assert primeiro.pedido is not None and repetido.pedido is not None
    assert primeiro.pedido.pedido_id == repetido.pedido.pedido_id
    assert repetido.pedido.idempotente
    assert repetido.pagamento is not None and repetido.pagamento.idempotente
    assert operacao.chamadas_pedido == 1
    assert operacao.chamadas_pagamento == 1


def test_catalogo_de_outro_tenant_nao_vaza() -> None:
    servico, _ = _servico()
    resultado = servico.interpretar(
        tenant_id="tenant-2",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia=_raw(),
        catalogo=_catalogo(),
    )
    assert resultado.estado is EstadoAtendimentoMica.HANDOFF_HUMANO
    assert resultado.handoff_motivo == "produto_nao_resolvido_exatamente"


def test_pagamento_na_entrega_permanece_aguardando_entrega() -> None:
    servico, _ = _servico(PagamentoStatus.PAGO)
    analisado = servico.interpretar(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        conversa_id="conv-1",
        mensagem_id="msg-1",
        raw_ia=_raw(),
        catalogo=_catalogo(),
    )
    assert analisado.carrinho is not None
    final = servico.confirmar(
        resultado=analisado,
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        cliente_ref="cliente-hash",
        confirmacao_cliente=True,
        fingerprint_confirmado=analisado.carrinho.fingerprint,
        metodo=MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        idempotency_key="confirm-entrega",
    )
    assert final.pagamento is not None
    assert final.pagamento.status is PagamentoStatus.AGUARDANDO_ENTREGA
