from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal

import pytest

from core.dominio.enums import PagamentoStatus, PedidoStatus
from core.entrega.modelos import StatusEntrega
from core.pagamentos.modelos import MetodoPagamento
from core.delivery.erros import ErroDelivery
from core.delivery.modelos import EnderecoDelivery, EstagioCancelamento, StatusCarrinhoDelivery
from core.delivery.runtime_teste import RuntimeDeliveryTeste


TENANT = "tenant-demo"
UNIDADE = "unidade-demo"
CLIENTE = "cliente-demo"


def _endereco(cep: str = "01001000") -> EnderecoDelivery:
    return EnderecoDelivery(
        endereco_id="end-1",
        cliente_ref=CLIENTE,
        cep=cep,
        logradouro="Praça da Sé",
        numero="100",
        bairro="Sé",
        cidade="São Paulo",
        uf="SP",
    )


def _pronto(runtime: RuntimeDeliveryTeste, carrinho_id: str = "cart-1"):
    carrinho = runtime.servico.abrir_carrinho(
        carrinho_id=carrinho_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
    )
    carrinho = runtime.servico.adicionar_item(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        produto_id="burger-teste",
        quantidade=1,
        expected_version=carrinho.versao,
        catalogo=runtime.catalogo,
    )
    return runtime.servico.definir_endereco(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        endereco=_endereco(),
        expected_version=carrinho.versao,
        areas=runtime.areas,
    )


def test_jornada_completa_cupom_cashback_pix_e_tracking() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    carrinho = runtime.servico.aplicar_cupom(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        codigo="BEMVINDO10",
        expected_version=carrinho.versao,
        cupons=runtime.cupons,
    )
    carrinho = runtime.servico.reservar_cashback(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        valor_desejado=Decimal("5"),
        expected_version=carrinho.versao,
    )
    assert carrinho.total == Decimal("30.80")
    resultado = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=carrinho.versao,
        metodo_pagamento=MetodoPagamento.PIX,
        idempotency_key="idem-1",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    assert resultado.pedido.total == Decimal("30.80")
    assert resultado.pedido.pagamento.status is PagamentoStatus.PENDENTE
    timeline = runtime.servico.acompanhar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
        pedido_id=resultado.pedido.pedido_id,
    )
    assert timeline[-1].status is StatusEntrega.AGUARDANDO_PRODUCAO


def test_pagamento_na_entrega_permanece_aguardando_entrega() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    resultado = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=carrinho.versao,
        metodo_pagamento=MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        idempotency_key="idem-entrega",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    assert resultado.pedido.pagamento.status is PagamentoStatus.AGUARDANDO_ENTREGA


def test_fora_da_area_e_bloqueado() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = runtime.servico.abrir_carrinho(
        carrinho_id="fora",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
    )
    with pytest.raises(ErroDelivery, match="fora_da_area_de_entrega"):
        runtime.servico.definir_endereco(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            carrinho_id=carrinho.carrinho_id,
            endereco=_endereco("99999999"),
            expected_version=carrinho.versao,
            areas=runtime.areas,
        )


def test_fechamento_revalida_preco_versao_e_estoque() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    alterado = replace(runtime.catalogo[0], preco=Decimal("35.00"), versao=2)
    with pytest.raises(ErroDelivery, match="catalogo_alterado_reconfirmacao"):
        runtime.servico.confirmar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            carrinho_id=carrinho.carrinho_id,
            expected_version=carrinho.versao,
            metodo_pagamento=MetodoPagamento.PIX,
            idempotency_key="preco-mudou",
            catalogo=(alterado, runtime.catalogo[1]),
            areas=runtime.areas,
        )
    atual = runtime.carrinhos.obter(
        tenant_id=TENANT, unidade_id=UNIDADE, carrinho_id=carrinho.carrinho_id
    )
    assert atual is not None
    assert atual.status is StatusCarrinhoDelivery.ABERTO


def test_fechamento_revalida_taxa_e_sla_versionados() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    nova_area = replace(runtime.areas[0], taxa=Decimal("9"), versao=2)
    with pytest.raises(ErroDelivery, match="cotacao_alterada_reconfirmacao"):
        runtime.servico.confirmar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            carrinho_id=carrinho.carrinho_id,
            expected_version=carrinho.versao,
            metodo_pagamento=MetodoPagamento.PIX,
            idempotency_key="area-mudou",
            catalogo=runtime.catalogo,
            areas=(nova_area,),
        )


def test_cashback_nunca_reserva_acima_do_saldo_autoritativo() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    carrinho = runtime.servico.reservar_cashback(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        valor_desejado=Decimal("999"),
        expected_version=carrinho.versao,
    )
    assert carrinho.cashback_reservado == Decimal("20.00")
    assert runtime.promocoes.saldo_cashback(
        tenant_id=TENANT, unidade_id=UNIDADE, cliente_ref=CLIENTE
    ) == Decimal("0.00")


def test_repetir_pedido_revalida_preco_area_e_nao_copia_promocao() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    confirmado = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=carrinho.versao,
        metodo_pagamento=MetodoPagamento.PIX,
        idempotency_key="pedido-original",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    novo_catalogo = (
        replace(runtime.catalogo[0], preco=Decimal("36"), versao=2),
        runtime.catalogo[1],
    )
    repetido = runtime.servico.repetir(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
        pedido_id=confirmado.pedido.pedido_id,
        novo_carrinho_id="cart-repeat",
        catalogo=novo_catalogo,
        areas=runtime.areas,
    )
    assert repetido.itens[0].preco_unitario == Decimal("36.00")
    assert repetido.desconto_cupom == Decimal("0.00")
    assert repetido.cashback_reservado == Decimal("0.00")
    assert repetido.cotacao is not None
    assert repetido.cotacao.taxa == Decimal("7.00")


def test_repeticao_nao_inventa_produto_indisponivel() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    confirmado = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=carrinho.versao,
        metodo_pagamento=MetodoPagamento.PIX,
        idempotency_key="original-sem-fallback",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    with pytest.raises(ErroDelivery, match="produto_indisponivel_repeticao"):
        runtime.servico.repetir(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_ref=CLIENTE,
            pedido_id=confirmado.pedido.pedido_id,
            novo_carrinho_id="repeat-falha",
            catalogo=(runtime.catalogo[1],),
            areas=runtime.areas,
        )


def test_cancelamento_reconcilia_pagamento_cashback_cupom_e_entrega() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    carrinho = runtime.servico.aplicar_cupom(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        codigo="BEMVINDO10",
        expected_version=carrinho.versao,
        cupons=runtime.cupons,
    )
    carrinho = runtime.servico.reservar_cashback(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        valor_desejado=Decimal("5"),
        expected_version=carrinho.versao,
    )
    confirmado = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=carrinho.versao,
        metodo_pagamento=MetodoPagamento.PIX,
        idempotency_key="cancelavel",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    runtime.pagamentos.marcar_pago(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        pedido_id=confirmado.pedido.pedido_id,
    )
    cancelado = runtime.servico.cancelar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
        pedido_id=confirmado.pedido.pedido_id,
        estagio=EstagioCancelamento.EM_PRODUCAO,
        motivo="Cliente desistiu",
        idempotency_key="cancel-1",
    )
    assert cancelado.pedido.status is PedidoStatus.CANCELADO
    assert cancelado.pedido.pagamento.status is PagamentoStatus.ESTORNADO
    assert cancelado.estorno_previsto == confirmado.pedido.total
    assert cancelado.desperdicio_estimado == Decimal("12.00")
    assert cancelado.cashback_restaurado == Decimal("5.00")
    assert cancelado.cupom_liberado is True
    assert runtime.promocoes.saldo_cashback(
        tenant_id=TENANT, unidade_id=UNIDADE, cliente_ref=CLIENTE
    ) == Decimal("20.00")
    timeline = runtime.servico.acompanhar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
        pedido_id=confirmado.pedido.pedido_id,
    )
    assert timeline[-1].status is StatusEntrega.CANCELADA


def test_pedido_entregue_nao_pode_ser_cancelado() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    confirmado = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=carrinho.versao,
        metodo_pagamento=MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        idempotency_key="entregue",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    entrega_id = confirmado.pedido.entrega_id
    for status, msg in (
        (StatusEntrega.AGUARDANDO_EXPEDICAO, "produção pronta"),
        (StatusEntrega.ATRIBUIDA, "entregador atribuído"),
        (StatusEntrega.COLETADA, "coletada"),
        (StatusEntrega.EM_ROTA, "em rota"),
        (StatusEntrega.ENTREGUE, "entregue"),
    ):
        runtime.entregas.avancar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            entrega_id=entrega_id,
            status=status,
            mensagem=msg,
        )
    with pytest.raises(ErroDelivery, match="pedido_entregue_nao_cancelavel"):
        runtime.servico.cancelar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_ref=CLIENTE,
            pedido_id=confirmado.pedido.pedido_id,
            estagio=EstagioCancelamento.ENTREGUE,
            motivo="tarde demais",
            idempotency_key="cancel-entregue",
        )


def test_isolamento_tenant_unidade_e_cliente_fail_closed() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    confirmado = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=carrinho.versao,
        metodo_pagamento=MetodoPagamento.PIX,
        idempotency_key="scope",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    with pytest.raises(ErroDelivery, match="recurso_indisponivel"):
        runtime.servico.acompanhar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_ref="outro-cliente",
            pedido_id=confirmado.pedido.pedido_id,
        )
    with pytest.raises(ErroDelivery, match="recurso_indisponivel"):
        runtime.servico.acompanhar(
            tenant_id="outro-tenant",
            unidade_id=UNIDADE,
            cliente_ref=CLIENTE,
            pedido_id=confirmado.pedido.pedido_id,
        )


def test_concorrencia_cas_permite_uma_mutacao_por_versao() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = runtime.servico.abrir_carrinho(
        carrinho_id="concorrente",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        cliente_ref=CLIENTE,
    )

    def adicionar() -> str:
        try:
            runtime.servico.adicionar_item(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                carrinho_id=carrinho.carrinho_id,
                produto_id="burger-teste",
                quantidade=1,
                expected_version=carrinho.versao,
                catalogo=runtime.catalogo,
            )
            return "ok"
        except ErroDelivery as exc:
            return exc.codigo

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: adicionar(), range(2)))
    assert resultados.count("ok") == 1
    assert resultados.count("conflito_concorrencia") == 1


def test_confirmacao_concorrente_nao_duplica_pedido_pagamento_ou_entrega() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime, "confirm-concorrente")

    def confirmar(chave: str) -> str:
        try:
            resultado = runtime.servico.confirmar(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                carrinho_id=carrinho.carrinho_id,
                expected_version=carrinho.versao,
                metodo_pagamento=MetodoPagamento.PIX,
                idempotency_key=chave,
                catalogo=runtime.catalogo,
                areas=runtime.areas,
            )
            return resultado.pedido.pedido_id
        except ErroDelivery as exc:
            return exc.codigo

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(confirmar, ("idem-a", "idem-b")))
    pedidos = [r for r in resultados if r.startswith("ped_")]
    assert len(pedidos) == 1
    assert any(
        r
        in {
            "conflito_concorrencia",
            "confirmacao_em_andamento_por_outro_comando",
            "carrinho_ja_confirmado",
        }
        for r in resultados
        if not r.startswith("ped_")
    )
    assert len(runtime.pedidos._dados) == 1
    assert len(runtime.pagamentos._por_pedido) == 1
    assert len(runtime.entregas._timeline) == 1


def test_retry_mesma_idempotencia_retorna_mesmo_pedido() -> None:
    runtime = RuntimeDeliveryTeste()
    carrinho = _pronto(runtime)
    primeiro = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=carrinho.versao,
        metodo_pagamento=MetodoPagamento.PIX,
        idempotency_key="retry",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    atual = runtime.carrinhos.obter(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
    )
    assert atual is not None
    segundo = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        carrinho_id=carrinho.carrinho_id,
        expected_version=atual.versao,
        metodo_pagamento=MetodoPagamento.PIX,
        idempotency_key="retry",
        catalogo=runtime.catalogo,
        areas=runtime.areas,
    )
    assert segundo.idempotente is True
    assert segundo.pedido.pedido_id == primeiro.pedido.pedido_id
