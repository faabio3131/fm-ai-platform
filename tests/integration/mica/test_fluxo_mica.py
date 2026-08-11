from decimal import Decimal

from core.dominio.enums import PagamentoStatus
from core.mica import (
    EstadoAtendimentoMica,
    OperacaoMicaFake,
    ProdutoCatalogoMica,
    ServicoMica,
)
from core.pagamentos.modelos import MetodoPagamento
from test_mode import mock_generate_content


def _servico():
    operacao = OperacaoMicaFake(status_pagamento=PagamentoStatus.PENDENTE)
    return ServicoMica(pedidos=operacao, pagamentos=operacao, handoff=operacao), operacao


def _catalogo():
    return (
        ProdutoCatalogoMica(
            produto_id="produto-1",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            nome="Burger Teste",
            preco=Decimal("29.90"),
        ),
    )


def test_mock_mica_vira_carrinho_e_pagamento_continua_pendente() -> None:
    servico, operacao = _servico()
    resposta = mock_generate_content(contents="Mica: quero um Burger Teste")
    analisado = servico.interpretar(
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        conversa_id="conv-e2e",
        mensagem_id="msg-e2e",
        raw_ia=resposta.text,
        catalogo=_catalogo(),
    )
    assert analisado.estado is EstadoAtendimentoMica.AGUARDANDO_CONFIRMACAO
    assert analisado.carrinho is not None
    assert analisado.carrinho.total == Decimal("29.90")
    assert operacao.chamadas_pedido == 0
    assert operacao.chamadas_pagamento == 0

    final = servico.confirmar(
        resultado=analisado,
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        cliente_ref="cliente-opaco",
        confirmacao_cliente=True,
        fingerprint_confirmado=analisado.carrinho.fingerprint,
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirmacao-e2e",
    )
    assert final.pedido is not None
    assert final.pagamento is not None
    assert final.pagamento.status is PagamentoStatus.PENDENTE
    assert operacao.chamadas_pedido == 1
    assert operacao.chamadas_pagamento == 1


def test_resposta_invalida_da_ia_vira_handoff_sem_efeito() -> None:
    servico, operacao = _servico()
    resposta = mock_generate_content(contents="Mica FM_AI_MOCK_INVALID")
    resultado = servico.interpretar(
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        conversa_id="conv-erro",
        mensagem_id="msg-erro",
        raw_ia=resposta.text,
        catalogo=_catalogo(),
    )
    assert resultado.estado is EstadoAtendimentoMica.HANDOFF_HUMANO
    assert resultado.handoff_motivo == "schema_mica_invalido"
    assert operacao.chamadas_pedido == 0
    assert operacao.chamadas_pagamento == 0
