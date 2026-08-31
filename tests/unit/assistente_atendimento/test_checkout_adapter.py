from datetime import datetime, timezone
from decimal import Decimal

import pytest

from application.checkout import ResultadoCheckoutV1
from core.assistente_atendimento.atendimento_modelos import (
    CarrinhoAtendimento,
    ItemCarrinhoAtendimento,
)
from core.assistente_atendimento.checkout_adapter import CheckoutAssistenteV1
from core.assistente_atendimento.erros import ErroAssistenteAtendimento
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.contexto import ContextoExecucao


def contexto(tenant="tenant-a", unidade="unidade-a"):
    return ContextoExecucao(
        tenant_id=tenant,
        unidade_id=unidade,
        usuario_id="agente",
        papeis=frozenset(),
        permissoes=frozenset(),
        correlation_id="corr-1",
        solicitado_em=datetime.now(timezone.utc),
        origem="teste.assistente",
        unidades_permitidas=frozenset({unidade}),
    )


def carrinho(tenant="tenant-a", unidade="unidade-a"):
    return CarrinhoAtendimento(
        tenant_id=tenant,
        unidade_id=unidade,
        conversa_id="conv-1",
        mensagem_id="msg-1",
        itens=(
            ItemCarrinhoAtendimento(
                produto_id="produto-1",
                nome_produto="X-Bacon",
                quantidade=2,
                preco_unitario=Decimal("25.00"),
            ),
        ),
        fingerprint="fp-1",
    )


def resultado_checkout_do_comando(comando):
    class ResultadoPedido:
        def __init__(self, pedido, idempotente=False):
            self.pedido = pedido
            self.idempotente = idempotente

    pedido_aguardando = comando.pedido.__class__(
        **{
            **comando.pedido.__dict__,
            "status": PedidoStatus.AGUARDANDO_CONFIRMACAO,
            "versao": 2,
        }
    )

    return ResultadoCheckoutV1(
        pedido=ResultadoPedido(comando.pedido),
        pagamento=None,
        reserva=None,
        aguardando_confirmacao=ResultadoPedido(pedido_aguardando),
    )


def test_adapter_constroi_pedido_whatsapp_no_escopo_correto():
    capturado = {}

    def executor(**kwargs):
        capturado.update(kwargs)
        return resultado_checkout_do_comando(kwargs["comando"])

    instante = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)

    adapter = CheckoutAssistenteV1(
        session_factory=lambda: None,
        executor=executor,
        agora=lambda: instante,
    )

    resultado = adapter.executar(
        contexto=contexto(),
        carrinho=carrinho(),
        cliente_ref="cliente-1",
        canal="whatsapp",
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirmacao-1",
    )

    comando = capturado["comando"]
    pedido = comando.pedido

    assert pedido.origem is OrigemPedido.WHATSAPP
    assert pedido.canal is CanalAtendimento.WHATSAPP
    assert pedido.status is PedidoStatus.RASCUNHO
    assert str(pedido.cliente_id) == "cliente-1"
    assert pedido.total.valor == Decimal("50.00")
    assert len(pedido.itens) == 1
    assert pedido.itens[0].quantidade.valor == 2
    assert comando.metodo_pagamento is MetodoPagamento.PIX
    assert comando.pagamento_id is not None
    assert capturado["contexto"].tenant_id == "tenant-a"
    assert resultado.pedido_status == "aguardando_confirmacao"


def test_adapter_rejeita_carrinho_de_outro_tenant():
    adapter = CheckoutAssistenteV1(
        session_factory=lambda: None,
        executor=lambda **kwargs: pytest.fail("executor não deveria ser chamado"),
    )

    with pytest.raises(
        ErroAssistenteAtendimento,
        match="carrinho_fora_do_contexto",
    ):
        adapter.executar(
            contexto=contexto(),
            carrinho=carrinho(tenant="tenant-b"),
            cliente_ref="cliente-1",
            canal="whatsapp",
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )


def test_adapter_rejeita_canal_nao_mapeado():
    adapter = CheckoutAssistenteV1(
        session_factory=lambda: None,
        executor=lambda **kwargs: pytest.fail("executor não deveria ser chamado"),
    )

    with pytest.raises(ErroAssistenteAtendimento) as exc_info:
        adapter.executar(
            contexto=contexto(),
            carrinho=carrinho(),
            cliente_ref="cliente-1",
            canal="canal-inventado",
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )

    assert exc_info.value.codigo == "canal_checkout_nao_suportado"
    assert exc_info.value.detalhe == "canal-inventado"


def test_pagamento_na_entrega_marca_recebimento_posterior():
    capturado = {}

    def executor(**kwargs):
        capturado.update(kwargs)
        return resultado_checkout_do_comando(kwargs["comando"])

    adapter = CheckoutAssistenteV1(
        session_factory=lambda: None,
        executor=executor,
    )

    adapter.executar(
        contexto=contexto(),
        carrinho=carrinho(),
        cliente_ref="cliente-1",
        canal="whatsapp",
        metodo=MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        idempotency_key="confirmacao-1",
    )

    assert capturado["comando"].recebimento_posterior is True


def test_ids_sao_deterministicos_em_replay():
    comandos = []

    def executor(**kwargs):
        comandos.append(kwargs["comando"])
        return resultado_checkout_do_comando(kwargs["comando"])

    instante = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
    adapter = CheckoutAssistenteV1(
        session_factory=lambda: None,
        executor=executor,
        agora=lambda: instante,
    )

    for _ in range(2):
        adapter.executar(
            contexto=contexto(),
            carrinho=carrinho(),
            cliente_ref="cliente-1",
            canal="whatsapp",
            metodo=MetodoPagamento.PIX,
            idempotency_key="mesma-confirmacao",
        )

    assert comandos[0].pedido.id == comandos[1].pedido.id
    assert comandos[0].pedido.idempotency_key == comandos[1].pedido.idempotency_key
    assert comandos[0].pagamento_id == comandos[1].pagamento_id
