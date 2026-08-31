from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.assistente_atendimento.atendimento_modelos import (
    EstadoAtendimento,
    ProdutoCatalogoAtendimento,
    ResultadoCheckoutAssistente,
)
from core.assistente_atendimento.atendimento_servicos import (
    ServicoAssistenteAtendimento,
)
from core.assistente_atendimento.contexto import (
    ClienteAtendimento,
    ContextoAtendimento,
    TipoClienteAtendimento,
)
from core.assistente_atendimento.entradas import (
    EntradaAtendimento,
    ModalidadeEntrada,
)
from core.assistente_atendimento.erros import ErroAssistenteAtendimento
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.contexto import ContextoExecucao


class CheckoutFake:
    def __init__(self) -> None:
        self.chamadas = []

    def executar(
        self,
        *,
        contexto,
        carrinho,
        cliente_ref,
        canal,
        metodo,
        idempotency_key,
    ):
        self.chamadas.append(
            (contexto, carrinho, cliente_ref, canal, metodo, idempotency_key)
        )
        return ResultadoCheckoutAssistente(
            pedido_id="pedido-1",
            pedido_status="aguardando_confirmacao",
            pagamento_id="pagamento-1",
            metodo_pagamento=metodo,
        )


class HandoffFake:
    def __init__(self) -> None:
        self.chamadas = []

    def registrar(self, *, contexto, conversa_id, motivo) -> None:
        self.chamadas.append((contexto, conversa_id, motivo))


def contexto_execucao(tenant="tenant-a", unidade="unidade-a"):
    return ContextoExecucao(
        tenant_id=tenant,
        unidade_id=unidade,
        usuario_id="agente-atendimento",
        papeis=frozenset(),
        permissoes=frozenset(),
        correlation_id="corr-1",
        solicitado_em=datetime.now(timezone.utc),
        origem="teste.assistente_atendimento",
        unidades_permitidas=frozenset({unidade}),
    )


def contexto_atendimento(
    *,
    tipo=TipoClienteAtendimento.CONHECIDO,
    tenant="tenant-a",
    unidade="unidade-a",
):
    cliente_ref = "cliente-1" if tipo is TipoClienteAtendimento.CONHECIDO else None
    return ContextoAtendimento(
        contexto_execucao=contexto_execucao(tenant, unidade),
        conversa_id="conv-1",
        canal="whatsapp",
        cliente=ClienteAtendimento(
            tipo=tipo,
            cliente_ref=cliente_ref,
            nome="João",
        ),
    )


def entrada_texto():
    return EntradaAtendimento(
        mensagem_id="msg-1",
        modalidade=ModalidadeEntrada.TEXTO,
        texto_original="Quero dois X-Bacon",
    )


def entrada_audio():
    return EntradaAtendimento(
        mensagem_id="msg-audio-1",
        modalidade=ModalidadeEntrada.AUDIO,
        transcricao="Quero dois X-Bacon",
    )


def catalogo():
    return (
        ProdutoCatalogoAtendimento(
            produto_id="prod-1",
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            nome="X-Bacon",
            preco=Decimal("25.00"),
        ),
    )


def raw_intencao():
    return (
        '{"cliente_nome":"João",'
        '"itens":[{"nome_produto":"X-Bacon","quantidade":2}],'
        '"resposta_cliente":"Dois X-Bacon"}'
    )


def test_cliente_conhecido_vai_para_confirmacao():
    checkout = CheckoutFake()
    handoff = HandoffFake()
    servico = ServicoAssistenteAtendimento(checkout=checkout, handoff=handoff)

    resultado = servico.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )

    assert resultado.estado is EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE
    assert resultado.carrinho is not None
    assert resultado.carrinho.total == Decimal("50.00")
    assert checkout.chamadas == []
    assert handoff.chamadas == []


def test_audio_transcrito_passa_pelo_mesmo_servico_deterministico():
    checkout = CheckoutFake()
    handoff = HandoffFake()
    servico = ServicoAssistenteAtendimento(checkout=checkout, handoff=handoff)

    resultado = servico.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_audio(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )

    assert resultado.estado is EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE
    assert resultado.carrinho is not None
    assert resultado.carrinho.total == Decimal("50.00")
    assert checkout.chamadas == []
    assert handoff.chamadas == []


def test_cliente_novo_nao_faz_checkout_antes_de_cadastro():
    checkout = CheckoutFake()
    handoff = HandoffFake()
    servico = ServicoAssistenteAtendimento(checkout=checkout, handoff=handoff)

    resultado = servico.interpretar(
        contexto=contexto_atendimento(tipo=TipoClienteAtendimento.NOVO),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )

    assert resultado.estado is EstadoAtendimento.AGUARDANDO_DADOS_CLIENTE
    assert resultado.carrinho is not None
    assert checkout.chamadas == []


def test_produto_de_outro_tenant_nao_pode_ser_resolvido():
    checkout = CheckoutFake()
    handoff = HandoffFake()
    servico = ServicoAssistenteAtendimento(checkout=checkout, handoff=handoff)

    catalogo_outro_tenant = (
        ProdutoCatalogoAtendimento(
            produto_id="prod-x",
            tenant_id="tenant-b",
            unidade_id="unidade-a",
            nome="X-Bacon",
            preco=Decimal("1.00"),
        ),
    )

    resultado = servico.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo_outro_tenant,
    )

    assert resultado.estado is EstadoAtendimento.HANDOFF_HUMANO
    assert resultado.handoff_motivo == "produto_nao_resolvido_exatamente"
    assert checkout.chamadas == []
    assert len(handoff.chamadas) == 1


def test_schema_invalido_falha_fechado_sem_checkout():
    checkout = CheckoutFake()
    handoff = HandoffFake()
    servico = ServicoAssistenteAtendimento(checkout=checkout, handoff=handoff)

    resultado = servico.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia="texto que não é json",
        catalogo=catalogo(),
    )

    assert resultado.estado is EstadoAtendimento.HANDOFF_HUMANO
    assert checkout.chamadas == []
    assert len(handoff.chamadas) == 1


def test_confirmacao_explicita_e_fingerprint_sao_obrigatorios():
    checkout = CheckoutFake()
    handoff = HandoffFake()
    servico = ServicoAssistenteAtendimento(checkout=checkout, handoff=handoff)
    contexto = contexto_atendimento()

    interpretado = servico.interpretar(
        contexto=contexto,
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )
    assert interpretado.carrinho is not None

    with pytest.raises(
        ErroAssistenteAtendimento,
        match="confirmacao_cliente_obrigatoria",
    ):
        servico.confirmar(
            contexto=contexto,
            resultado=interpretado,
            confirmacao_cliente=False,
            fingerprint_confirmado=interpretado.carrinho.fingerprint,
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )

    with pytest.raises(
        ErroAssistenteAtendimento,
        match="carrinho_alterado_reconfirmacao_obrigatoria",
    ):
        servico.confirmar(
            contexto=contexto,
            resultado=interpretado,
            confirmacao_cliente=True,
            fingerprint_confirmado="fingerprint-diferente",
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )

    assert checkout.chamadas == []


def test_confirmacao_valida_chama_checkout_uma_vez():
    checkout = CheckoutFake()
    handoff = HandoffFake()
    servico = ServicoAssistenteAtendimento(checkout=checkout, handoff=handoff)
    contexto = contexto_atendimento()

    interpretado = servico.interpretar(
        contexto=contexto,
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )
    assert interpretado.carrinho is not None

    resultado = servico.confirmar(
        contexto=contexto,
        resultado=interpretado,
        confirmacao_cliente=True,
        fingerprint_confirmado=interpretado.carrinho.fingerprint,
        metodo=MetodoPagamento.PIX,
        idempotency_key="confirmacao-1",
    )

    assert resultado.estado is EstadoAtendimento.CHECKOUT_REGISTRADO
    assert resultado.checkout is not None
    assert resultado.checkout.pedido_id == "pedido-1"
    assert len(checkout.chamadas) == 1
    assert handoff.chamadas == []
