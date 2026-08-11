from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.dominio.enums import PagamentoStatus, PedidoStatus
from core.entrega.modelos import StatusEntrega
from core.pagamentos.modelos import MetodoPagamento
from core.delivery.erros import ErroDelivery
from core.delivery.modelos import (
    AreaEntrega,
    CarrinhoDelivery,
    CotacaoEntrega,
    CupomDelivery,
    EnderecoDelivery,
    EventoTracking,
    ItemCarrinhoDelivery,
    PagamentoDeliveryRef,
    PedidoDelivery,
    ProdutoDelivery,
    StatusCarrinhoDelivery,
    TipoCupom,
    moeda,
)


def test_moeda_arredonda_e_rejeita_negativo() -> None:
    assert moeda(Decimal("10.125")) == Decimal("10.13")
    with pytest.raises(ErroDelivery, match="valor_monetario_negativo"):
        moeda(Decimal("-0.01"))


def test_endereco_normaliza_cep_e_uf() -> None:
    endereco = EnderecoDelivery(
        endereco_id="e1",
        cliente_ref="c1",
        cep="01001-000",
        logradouro="Praça da Sé",
        numero="1",
        bairro="Sé",
        cidade="São Paulo",
        uf="sp",
    )
    assert endereco.cep == "01001000"
    assert endereco.uf == "SP"


def test_endereco_rejeita_cep_invalido() -> None:
    with pytest.raises(ErroDelivery, match="cep_invalido"):
        EnderecoDelivery(
            endereco_id="e1",
            cliente_ref="c1",
            cep="123",
            logradouro="Rua",
            numero="1",
            bairro="Centro",
            cidade="Cidade",
            uf="SP",
        )


def test_area_valida_taxa_sla_e_prefixos() -> None:
    area = AreaEntrega(
        area_id="a1",
        tenant_id="t1",
        unidade_id="u1",
        nome="Centro",
        prefixos_cep=("010", "01001"),
        taxa=Decimal("7"),
        sla_minutos=30,
        sla_maxutos=45,
        versao=1,
    )
    assert area.taxa == Decimal("7.00")
    assert area.prefixos_cep == ("010", "01001")


def test_cupom_percentual_respeita_minimo() -> None:
    agora = datetime.now(timezone.utc)
    cupom = CupomDelivery(
        codigo=" dez ",
        tenant_id="t",
        unidade_id="u",
        tipo=TipoCupom.PERCENTUAL,
        valor=Decimal("10"),
        minimo_pedido=Decimal("20"),
        inicio=agora - timedelta(hours=1),
        fim=agora + timedelta(hours=1),
    )
    assert cupom.codigo == "DEZ"
    assert cupom.calcular_desconto(Decimal("32")) == Decimal("3.20")
    with pytest.raises(ErroDelivery, match="cupom_minimo_nao_atingido"):
        cupom.calcular_desconto(Decimal("10"))


def test_carrinho_calcula_total_com_taxa_cupom_e_cashback() -> None:
    item = ItemCarrinhoDelivery(
        produto_id="p1",
        nome="Burger",
        quantidade=2,
        preco_unitario=Decimal("20"),
        custo_estimado_unitario=Decimal("8"),
        produto_versao=1,
    )
    carrinho = CarrinhoDelivery(
        carrinho_id="c1",
        tenant_id="t1",
        unidade_id="u1",
        cliente_ref="cli1",
        versao=4,
        status=StatusCarrinhoDelivery.ABERTO,
        itens=(item,),
        cotacao=CotacaoEntrega(
            area_id="a1",
            nome_area="Centro",
            taxa=Decimal("7"),
            sla_minutos=30,
            sla_maxutos=45,
            versao_area=1,
        ),
        desconto_cupom=Decimal("5"),
        cashback_reservado=Decimal("10"),
    )
    assert carrinho.subtotal == Decimal("40.00")
    assert carrinho.total == Decimal("32.00")
    assert carrinho.custo_estimado_itens == Decimal("16.00")


def test_produto_rejeita_estoque_negativo() -> None:
    with pytest.raises(ErroDelivery, match="estoque_invalido"):
        ProdutoDelivery(
            produto_id="p",
            tenant_id="t",
            unidade_id="u",
            nome="Produto",
            preco=Decimal("1"),
            estoque_disponivel=Decimal("-1"),
        )


def test_carrinho_em_confirmacao_exige_pedido_e_idempotencia() -> None:
    with pytest.raises(ErroDelivery, match="carrinho_confirmacao_inconsistente"):
        CarrinhoDelivery(
            carrinho_id="c",
            tenant_id="t",
            unidade_id="u",
            cliente_ref="cli",
            versao=2,
            status=StatusCarrinhoDelivery.CONFIRMACAO_EM_ANDAMENTO,
        )


def test_tracking_exige_timestamp_com_timezone() -> None:
    with pytest.raises(ErroDelivery, match="timestamp_sem_timezone"):
        EventoTracking(
            entrega_id="e",
            status=StatusEntrega.AGUARDANDO_PRODUCAO,
            mensagem="Aguardando",
            ocorrido_em=datetime.now(),
        )


def test_pedido_delivery_preserva_autoridades_financeira_e_logistica() -> None:
    endereco = EnderecoDelivery(
        endereco_id="e",
        cliente_ref="cli",
        cep="01001000",
        logradouro="Rua",
        numero="1",
        bairro="Centro",
        cidade="São Paulo",
        uf="SP",
    )
    cotacao = CotacaoEntrega(
        area_id="a",
        nome_area="Centro",
        taxa=Decimal("7"),
        sla_minutos=30,
        sla_maxutos=45,
        versao_area=1,
    )
    item = ItemCarrinhoDelivery(
        produto_id="p",
        nome="Produto",
        quantidade=1,
        preco_unitario=Decimal("20"),
        custo_estimado_unitario=Decimal("8"),
        produto_versao=1,
    )
    pedido = PedidoDelivery(
        pedido_id="ped",
        tenant_id="t",
        unidade_id="u",
        cliente_ref="cli",
        carrinho_id="cart",
        itens=(item,),
        endereco=endereco,
        cotacao=cotacao,
        desconto_cupom=Decimal("0"),
        cashback_usado=Decimal("0"),
        total=Decimal("27"),
        pagamento=PagamentoDeliveryRef(
            pagamento_id="pay",
            status=PagamentoStatus.PENDENTE,
            metodo=MetodoPagamento.PIX,
        ),
        entrega_id="ent",
    )
    assert pedido.status is PedidoStatus.CONFIRMADO
    assert pedido.pagamento.status is PagamentoStatus.PENDENTE
