from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.assistente_atendimento.atendimento_modelos import (
    CotacaoEntregaAtendimento,
    EstadoAtendimento,
    ModalidadePedidoAtendimento,
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

    def registrar(
        self,
        *,
        contexto,
        conversa_id,
        motivo,
        metadata_segura=None,
    ) -> None:
        self.chamadas.append(
            (contexto, conversa_id, motivo, metadata_segura or {})
        )


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


def raw_intencao(modalidade="retirada", endereco=None):
    endereco_json = "null" if endereco is None else f'"{endereco}"'
    return (
        '{"cliente_nome":"João",'
        '"itens":[{"nome_produto":"X-Bacon","quantidade":2}],'
        '"resposta_cliente":"Dois X-Bacon",'
        f'"modalidade":"{modalidade}",'
        f'"endereco_texto":{endereco_json}'
        "}"
    )


def cotacao():
    return CotacaoEntregaAtendimento(
        endereco_formatado="Rua A, 10 - Centro, Cidade - SP, 01000-000",
        cep="01000000",
        place_id="place-1",
        latitude=-23.5,
        longitude=-46.6,
        distancia_metros=4200,
        eta_rota_minutos=15,
        area_id="centro",
        nome_area="Centro",
        taxa=Decimal("8.00"),
        sla_minutos=35,
        sla_maxutos=55,
        versao_area=3,
    )


def servico():
    checkout = CheckoutFake()
    handoff = HandoffFake()
    return ServicoAssistenteAtendimento(checkout=checkout, handoff=handoff), checkout, handoff


def test_cliente_conhecido_retirada_vai_para_confirmacao():
    srv, checkout, handoff = servico()
    resultado = srv.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )
    assert resultado.estado is EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO
    assert resultado.carrinho is not None
    assert resultado.carrinho.total == Decimal("50.00")
    assert resultado.carrinho.modalidade is ModalidadePedidoAtendimento.RETIRADA
    assert checkout.chamadas == []
    assert handoff.chamadas == []


def test_audio_transcrito_passa_pelo_mesmo_servico_deterministico():
    srv, checkout, handoff = servico()
    resultado = srv.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_audio(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )
    assert resultado.estado is EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO
    assert resultado.carrinho is not None
    assert resultado.carrinho.total == Decimal("50.00")
    assert checkout.chamadas == []
    assert handoff.chamadas == []


def test_modalidade_indefinida_bloqueia_confirmacao():
    srv, checkout, _ = servico()
    resultado = srv.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(modalidade="indefinida"),
        catalogo=catalogo(),
    )
    assert resultado.estado is EstadoAtendimento.AGUARDANDO_MODALIDADE_ENTREGA
    with pytest.raises(ErroAssistenteAtendimento, match="atendimento_nao_confirmavel"):
        srv.confirmar(
            contexto=contexto_atendimento(),
            resultado=resultado,
            confirmacao_cliente=True,
            fingerprint_confirmado=resultado.carrinho.fingerprint,
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )
    assert checkout.chamadas == []


def test_entrega_sem_cotacao_bloqueia_checkout():
    srv, checkout, _ = servico()
    resultado = srv.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(
            modalidade="entrega",
            endereco="Rua A, 10, CEP 01000-000",
        ),
        catalogo=catalogo(),
    )
    assert resultado.estado is EstadoAtendimento.AGUARDANDO_ENDERECO_ENTREGA
    with pytest.raises(ErroAssistenteAtendimento, match="atendimento_nao_confirmavel"):
        srv.confirmar(
            contexto=contexto_atendimento(),
            resultado=resultado,
            confirmacao_cliente=True,
            fingerprint_confirmado=resultado.carrinho.fingerprint,
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )
    assert checkout.chamadas == []


def test_cotacao_entrega_altera_fingerprint_taxa_total_e_exige_reconfirmacao():
    srv, checkout, _ = servico()
    contexto = contexto_atendimento()
    inicial = srv.interpretar(
        contexto=contexto,
        entrada=entrada_texto(),
        raw_ia=raw_intencao(
            modalidade="entrega",
            endereco="Rua A, 10, CEP 01000-000",
        ),
        catalogo=catalogo(),
    )
    assert inicial.carrinho is not None
    fingerprint_inicial = inicial.carrinho.fingerprint

    atualizado = srv.aplicar_cotacao_entrega(
        contexto=contexto,
        resultado=inicial,
        cotacao=cotacao(),
    )

    assert atualizado.estado is EstadoAtendimento.AGUARDANDO_FORMA_PAGAMENTO
    assert atualizado.carrinho is not None
    assert atualizado.carrinho.fingerprint != fingerprint_inicial
    assert atualizado.carrinho.taxa_entrega == Decimal("8.00")
    assert atualizado.carrinho.total == Decimal("58.00")

    com_pagamento = srv.definir_pagamento(
        resultado=atualizado,
        metodo=MetodoPagamento.PIX,
    )
    assert com_pagamento.estado is EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE
    assert com_pagamento.carrinho is not None
    assert com_pagamento.carrinho.fingerprint != atualizado.carrinho.fingerprint

    with pytest.raises(
        ErroAssistenteAtendimento,
        match="carrinho_alterado_reconfirmacao_obrigatoria",
    ):
        srv.confirmar(
            contexto=contexto,
            resultado=com_pagamento,
            confirmacao_cliente=True,
            fingerprint_confirmado=fingerprint_inicial,
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )
    assert checkout.chamadas == []


def test_dinheiro_com_troco_entra_no_fingerprint_e_na_confirmacao():
    srv, checkout, _ = servico()
    contexto = contexto_atendimento()
    interpretado = srv.interpretar(
        contexto=contexto,
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )
    assert interpretado.carrinho is not None
    fingerprint_sem_pagamento = interpretado.carrinho.fingerprint

    atualizado = srv.definir_pagamento(
        resultado=interpretado,
        metodo=MetodoPagamento.DINHEIRO,
        valor_para_troco=Decimal("100.00"),
    )

    assert atualizado.estado is EstadoAtendimento.AGUARDANDO_CONFIRMACAO_CLIENTE
    assert atualizado.carrinho is not None
    assert atualizado.carrinho.fingerprint != fingerprint_sem_pagamento
    assert atualizado.carrinho.pagamento is not None
    assert atualizado.carrinho.pagamento.metodo is MetodoPagamento.DINHEIRO
    assert atualizado.carrinho.pagamento.troco_estimado(
        atualizado.carrinho.total
    ) == Decimal("50.00")

    with pytest.raises(
        ErroAssistenteAtendimento,
        match="forma_pagamento_alterada_reconfirmacao_obrigatoria",
    ):
        srv.confirmar(
            contexto=contexto,
            resultado=atualizado,
            confirmacao_cliente=True,
            fingerprint_confirmado=atualizado.carrinho.fingerprint,
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )
    assert checkout.chamadas == []


def test_troco_inferior_ao_total_falha_fechado_sem_checkout():
    srv, checkout, _ = servico()
    interpretado = srv.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )

    with pytest.raises(
        ErroAssistenteAtendimento,
        match="valor_para_troco_inferior_total",
    ):
        srv.definir_pagamento(
            resultado=interpretado,
            metodo=MetodoPagamento.DINHEIRO,
            valor_para_troco=Decimal("40.00"),
        )
    assert checkout.chamadas == []


def test_cliente_novo_nao_faz_checkout_antes_de_cadastro():
    srv, checkout, _ = servico()
    resultado = srv.interpretar(
        contexto=contexto_atendimento(tipo=TipoClienteAtendimento.NOVO),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )
    assert resultado.estado is EstadoAtendimento.AGUARDANDO_DADOS_CLIENTE
    assert resultado.carrinho is not None
    assert checkout.chamadas == []


def test_produto_de_outro_tenant_nao_pode_ser_resolvido():
    srv, checkout, handoff = servico()
    catalogo_outro_tenant = (
        ProdutoCatalogoAtendimento(
            produto_id="prod-x",
            tenant_id="tenant-b",
            unidade_id="unidade-a",
            nome="X-Bacon",
            preco=Decimal("1.00"),
        ),
    )
    resultado = srv.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo_outro_tenant,
    )
    assert resultado.estado is EstadoAtendimento.HANDOFF_HUMANO
    assert resultado.handoff_motivo == "produto_nao_resolvido_exatamente"
    assert checkout.chamadas == []
    assert len(handoff.chamadas) == 1


def test_handoff_carrega_contexto_minimizado_sem_pii():
    srv, checkout, handoff = servico()
    resultado = srv.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia=raw_intencao(produto="Produto inexistente"),
        catalogo=catalogo(),
    )

    assert resultado.estado is EstadoAtendimento.HANDOFF_HUMANO
    assert checkout.chamadas == []
    assert len(handoff.chamadas) == 1
    metadata = handoff.chamadas[0][3]
    assert metadata["cliente_ref"] == "cliente-1"
    assert metadata["cliente_tipo"] == "conhecido"
    assert metadata["itens_solicitados"] == 1
    assert metadata["itens_resolvidos"] == 0
    assert "telefone" not in metadata
    assert "endereco" not in metadata


def test_schema_invalido_falha_fechado_sem_checkout():
    srv, checkout, handoff = servico()
    resultado = srv.interpretar(
        contexto=contexto_atendimento(),
        entrada=entrada_texto(),
        raw_ia="texto que não é json",
        catalogo=catalogo(),
    )
    assert resultado.estado is EstadoAtendimento.HANDOFF_HUMANO
    assert checkout.chamadas == []
    assert len(handoff.chamadas) == 1


def test_confirmacao_explicita_e_fingerprint_sao_obrigatorios():
    srv, checkout, _ = servico()
    contexto = contexto_atendimento()
    interpretado = srv.interpretar(
        contexto=contexto,
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )
    assert interpretado.carrinho is not None
    interpretado = srv.definir_pagamento(
        resultado=interpretado,
        metodo=MetodoPagamento.PIX,
    )
    assert interpretado.carrinho is not None

    with pytest.raises(ErroAssistenteAtendimento, match="confirmacao_cliente_obrigatoria"):
        srv.confirmar(
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
        srv.confirmar(
            contexto=contexto,
            resultado=interpretado,
            confirmacao_cliente=True,
            fingerprint_confirmado="fingerprint-diferente",
            metodo=MetodoPagamento.PIX,
            idempotency_key="confirmacao-1",
        )
    assert checkout.chamadas == []


def test_confirmacao_valida_chama_checkout_uma_vez():
    srv, checkout, handoff = servico()
    contexto = contexto_atendimento()
    interpretado = srv.interpretar(
        contexto=contexto,
        entrada=entrada_texto(),
        raw_ia=raw_intencao(),
        catalogo=catalogo(),
    )
    assert interpretado.carrinho is not None
    interpretado = srv.definir_pagamento(
        resultado=interpretado,
        metodo=MetodoPagamento.PIX,
    )
    assert interpretado.carrinho is not None

    resultado = srv.confirmar(
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
