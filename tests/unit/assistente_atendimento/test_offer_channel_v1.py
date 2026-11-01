"""WhatsApp governed offers: conversational accept/refuse and state continuity."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from application.assistente_atendimento_runtime import ResultadoRuntimeAssistente
from application.assistente_channel_runtime import (
    RuntimeCanalWhatsAppV1,
    _serializar_runtime,
)
from core.assistente_atendimento.atendimento_modelos import (
    CarrinhoAtendimento,
    EstadoAtendimento,
    ItemCarrinhoAtendimento,
    ModalidadePedidoAtendimento,
    ResultadoAtendimento,
    SugestaoProdutoAtendimento,
)
from core.assistente_atendimento.contexto import (
    ClienteAtendimento,
    ContextoAtendimento,
    TipoClienteAtendimento,
)
from core.seguranca.contexto import ContextoExecucao


def _runtime():
    contexto = ContextoAtendimento(
        contexto_execucao=ContextoExecucao.sistema(
            identidade="teste-oferta",
            motivo="teste seguro do canal",
            tenant_id="t1",
            unidade_id="u1",
            correlation_id="corr",
            solicitado_em=datetime.now(timezone.utc),
        ),
        conversa_id="c1",
        canal="whatsapp",
        cliente=ClienteAtendimento(
            tipo=TipoClienteAtendimento.CONHECIDO,
            cliente_ref="cl1",
        ),
    )
    carrinho = CarrinhoAtendimento(
        tenant_id="t1",
        unidade_id="u1",
        conversa_id="c1",
        mensagem_id="m1",
        itens=(ItemCarrinhoAtendimento(
            produto_id="p1", nome_produto="Hamburguer", quantidade=1,
            preco_unitario=Decimal("25.00"),
        ),),
        fingerprint="original",
        modalidade=ModalidadePedidoAtendimento.RETIRADA,
    )
    return ResultadoRuntimeAssistente(
        contexto=contexto,
        resultado=ResultadoAtendimento(
            estado=EstadoAtendimento.AGUARDANDO_RESPOSTA_OFERTA,
            mensagem="Quer Refrigerante?",
            carrinho=carrinho,
            sugestao=SugestaoProdutoAtendimento(
                produto_id="p2", nome="Refrigerante",
                preco=Decimal("8.00"),
            ),
        ),
    )


class FakeRuntime:
    def __init__(self):
        self.chamadas = []

    def responder_oferta(self, *, runtime_anterior, aceitar):
        self.chamadas.append(aceitar)
        return ResultadoRuntimeAssistente(
            contexto=runtime_anterior.contexto,
            resultado=replace(
                runtime_anterior.resultado,
                estado=EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO,
                mensagem="Informe a forma de pagamento",
                sugestao=None,
            ),
        )


def test_aceite_expresso_no_whatsapp_ativa_transicao_uma_vez():
    fake = FakeRuntime()
    canal = RuntimeCanalWhatsAppV1(lambda: None, runtime=fake, handoff=object())
    atual = canal._avancar(runtime=_runtime(), texto="Sim, por favor!",
                           recipient="5511999999999", mensagem_id="m2")
    assert fake.chamadas == [True]
    assert atual.resultado.estado is EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO


def test_recusa_expresso_no_whatsapp_ativa_transicao_sem_adicionar():
    fake = FakeRuntime()
    canal = RuntimeCanalWhatsAppV1(lambda: None, runtime=fake, handoff=object())
    atual = canal._avancar(runtime=_runtime(), texto="Não, obrigado.",
                           recipient="5511999999999", mensagem_id="m2")
    assert fake.chamadas == [False]
    assert atual.resultado.estado is EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO


def test_resposta_ambigua_nao_inclui_produtos_automaticamente():
    fake = FakeRuntime()
    canal = RuntimeCanalWhatsAppV1(lambda: None, runtime=fake, handoff=object())
    atual = canal._avancar(runtime=_runtime(), texto="Talvez depois",
                           recipient="5511999999999", mensagem_id="m2")
    assert fake.chamadas == []
    assert atual.resultado.estado is EstadoAtendimento.AGUARDANDO_RESPOSTA_OFERTA
    assert atual.resultado.sugestao is not None


def test_oferta_serializada_para_replay_seguro_no_canal():
    payload = _serializar_runtime(_runtime())
    oferta = payload["resultado"]["sugestao"]
    assert oferta == {"produto_id": "p2", "nome": "Refrigerante", "preco": "8.00", "tipo": "cross_sell", "substitui_produto_id": None}
    assert payload["resultado"]["estado"] == "aguardando_resposta_oferta"
