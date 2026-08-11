"""Serviços determinísticos do Delivery Próprio V1."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from core.dominio.enums import PagamentoStatus, PedidoStatus
from core.entrega.modelos import StatusEntrega
from core.pagamentos.modelos import MetodoPagamento

from .adapters import (
    PortaCarrinhosDelivery,
    PortaEntregaCanalDelivery,
    PortaPagamentosDelivery,
    PortaPedidosDelivery,
    PortaPromocoesDelivery,
)
from .erros import ErroDelivery
from .modelos import (
    AreaEntrega,
    CarrinhoDelivery,
    CotacaoEntrega,
    CupomDelivery,
    EnderecoDelivery,
    EstagioCancelamento,
    EventoTracking,
    ItemCarrinhoDelivery,
    PedidoDelivery,
    ProdutoDelivery,
    ResultadoCancelamentoDelivery,
    ResultadoConfirmacaoDelivery,
    StatusCarrinhoDelivery,
    moeda,
)


def _id(prefixo: str, chave: str) -> str:
    digest = hashlib.sha256(chave.encode("utf-8")).hexdigest()[:24]
    return f"{prefixo}_{digest}"


def _catalogo_por_id(
    catalogo: Iterable[ProdutoDelivery], *, tenant_id: str, unidade_id: str
) -> dict[str, ProdutoDelivery]:
    resultado: dict[str, ProdutoDelivery] = {}
    for produto in catalogo:
        if (
            produto.tenant_id == tenant_id
            and produto.unidade_id == unidade_id
            and produto.ativo
        ):
            if produto.produto_id in resultado:
                raise ErroDelivery("catalogo_duplicado")
            resultado[produto.produto_id] = produto
    return resultado


def _area_para_cep(
    areas: Iterable[AreaEntrega],
    *,
    tenant_id: str,
    unidade_id: str,
    cep: str,
) -> AreaEntrega:
    candidatas: list[tuple[int, AreaEntrega]] = []
    for area in areas:
        if (
            area.tenant_id != tenant_id
            or area.unidade_id != unidade_id
            or not area.ativa
        ):
            continue
        tamanhos = [
            len(prefixo) for prefixo in area.prefixos_cep if cep.startswith(prefixo)
        ]
        if tamanhos:
            candidatas.append((max(tamanhos), area))
    if not candidatas:
        raise ErroDelivery("fora_da_area_de_entrega")
    maior = max(tamanho for tamanho, _ in candidatas)
    melhores = [area for tamanho, area in candidatas if tamanho == maior]
    if len(melhores) != 1:
        raise ErroDelivery("area_de_entrega_ambigua")
    return melhores[0]


class ServicoDelivery:
    def __init__(
        self,
        *,
        carrinhos: PortaCarrinhosDelivery,
        pedidos: PortaPedidosDelivery,
        pagamentos: PortaPagamentosDelivery,
        entregas: PortaEntregaCanalDelivery,
        promocoes: PortaPromocoesDelivery,
    ) -> None:
        self.carrinhos = carrinhos
        self.pedidos = pedidos
        self.pagamentos = pagamentos
        self.entregas = entregas
        self.promocoes = promocoes

    def abrir_carrinho(
        self,
        *,
        carrinho_id: str,
        tenant_id: str,
        unidade_id: str,
        cliente_ref: str,
    ) -> CarrinhoDelivery:
        carrinho = CarrinhoDelivery(
            carrinho_id=carrinho_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_ref=cliente_ref,
            versao=1,
            status=StatusCarrinhoDelivery.ABERTO,
        )
        return self.carrinhos.criar(carrinho)

    def _carrinho(
        self, *, tenant_id: str, unidade_id: str, carrinho_id: str
    ) -> CarrinhoDelivery:
        carrinho = self.carrinhos.obter(
            tenant_id=tenant_id, unidade_id=unidade_id, carrinho_id=carrinho_id
        )
        if carrinho is None:
            raise ErroDelivery("recurso_indisponivel")
        return carrinho

    @staticmethod
    def _aberto(carrinho: CarrinhoDelivery) -> None:
        if carrinho.status is not StatusCarrinhoDelivery.ABERTO:
            raise ErroDelivery("carrinho_nao_editavel")

    def adicionar_item(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        carrinho_id: str,
        produto_id: str,
        quantidade: int,
        expected_version: int,
        catalogo: Iterable[ProdutoDelivery],
    ) -> CarrinhoDelivery:
        carrinho = self._carrinho(
            tenant_id=tenant_id, unidade_id=unidade_id, carrinho_id=carrinho_id
        )
        self._aberto(carrinho)
        if carrinho.versao != expected_version:
            raise ErroDelivery("conflito_concorrencia")
        produtos = _catalogo_por_id(
            catalogo, tenant_id=tenant_id, unidade_id=unidade_id
        )
        produto = produtos.get(produto_id)
        if produto is None:
            raise ErroDelivery("produto_indisponivel")
        atual = next((i for i in carrinho.itens if i.produto_id == produto_id), None)
        nova_quantidade = quantidade + (atual.quantidade if atual else 0)
        if quantidade < 1 or nova_quantidade > 100:
            raise ErroDelivery("quantidade_invalida")
        if Decimal(nova_quantidade) > produto.estoque_disponivel:
            raise ErroDelivery("estoque_indisponivel")
        novo_item = ItemCarrinhoDelivery(
            produto_id=produto.produto_id,
            nome=produto.nome,
            quantidade=nova_quantidade,
            preco_unitario=produto.preco,
            custo_estimado_unitario=produto.custo_estimado,
            produto_versao=produto.versao,
        )
        itens = tuple(i for i in carrinho.itens if i.produto_id != produto_id) + (
            novo_item,
        )
        novo = replace(carrinho, itens=itens, versao=carrinho.versao + 1)
        return self.carrinhos.salvar_cas(novo, expected_version=expected_version)

    def definir_endereco(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        carrinho_id: str,
        endereco: EnderecoDelivery,
        expected_version: int,
        areas: Iterable[AreaEntrega],
    ) -> CarrinhoDelivery:
        carrinho = self._carrinho(
            tenant_id=tenant_id, unidade_id=unidade_id, carrinho_id=carrinho_id
        )
        self._aberto(carrinho)
        if carrinho.versao != expected_version:
            raise ErroDelivery("conflito_concorrencia")
        if endereco.cliente_ref != carrinho.cliente_ref:
            raise ErroDelivery("endereco_de_outro_cliente")
        if not endereco.validado:
            raise ErroDelivery("endereco_nao_validado")
        area = _area_para_cep(
            areas,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cep=endereco.cep,
        )
        cotacao = CotacaoEntrega(
            area_id=area.area_id,
            nome_area=area.nome,
            taxa=area.taxa,
            sla_minutos=area.sla_minutos,
            sla_maxutos=area.sla_maxutos,
            versao_area=area.versao,
        )
        novo = replace(
            carrinho,
            endereco=endereco,
            cotacao=cotacao,
            versao=carrinho.versao + 1,
        )
        return self.carrinhos.salvar_cas(novo, expected_version=expected_version)

    def aplicar_cupom(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        carrinho_id: str,
        codigo: str,
        expected_version: int,
        cupons: Iterable[CupomDelivery],
        agora: datetime | None = None,
    ) -> CarrinhoDelivery:
        carrinho = self._carrinho(
            tenant_id=tenant_id, unidade_id=unidade_id, carrinho_id=carrinho_id
        )
        self._aberto(carrinho)
        if carrinho.versao != expected_version:
            raise ErroDelivery("conflito_concorrencia")
        codigo_norm = codigo.strip().upper()
        if carrinho.cupom_codigo and carrinho.cupom_codigo != codigo_norm:
            raise ErroDelivery("cupom_ja_aplicado")
        cupom = next(
            (
                c
                for c in cupons
                if c.codigo == codigo_norm
                and c.tenant_id == tenant_id
                and c.unidade_id == unidade_id
            ),
            None,
        )
        if cupom is None or not cupom.ativo:
            raise ErroDelivery("cupom_invalido")
        agora = agora or datetime.now(timezone.utc)
        agora = agora.astimezone(timezone.utc)
        if agora < cupom.inicio or agora > cupom.fim:
            raise ErroDelivery("cupom_fora_vigencia")
        desconto = cupom.calcular_desconto(carrinho.subtotal)
        reservado = self.promocoes.reservar_cupom(
            cupom=cupom,
            cliente_ref=carrinho.cliente_ref,
            carrinho_id=carrinho.carrinho_id,
            desconto=str(desconto),
            idempotency_key=f"delivery:cupom:{carrinho.carrinho_id}:{cupom.codigo}",
        )
        if moeda(reservado) != desconto:
            raise ErroDelivery("reserva_cupom_inconsistente")
        novo = replace(
            carrinho,
            cupom_codigo=cupom.codigo,
            desconto_cupom=desconto,
            versao=carrinho.versao + 1,
        )
        return self.carrinhos.salvar_cas(novo, expected_version=expected_version)

    def reservar_cashback(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        carrinho_id: str,
        valor_desejado: Decimal,
        expected_version: int,
    ) -> CarrinhoDelivery:
        carrinho = self._carrinho(
            tenant_id=tenant_id, unidade_id=unidade_id, carrinho_id=carrinho_id
        )
        self._aberto(carrinho)
        if carrinho.versao != expected_version:
            raise ErroDelivery("conflito_concorrencia")
        if carrinho.cashback_reservado > 0:
            raise ErroDelivery("cashback_ja_reservado")
        maximo = min(
            moeda(valor_desejado),
            moeda(carrinho.subtotal + carrinho.taxa_entrega - carrinho.desconto_cupom),
        )
        reservado = moeda(
            self.promocoes.reservar_cashback(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                cliente_ref=carrinho.cliente_ref,
                carrinho_id=carrinho.carrinho_id,
                valor_maximo=str(maximo),
                idempotency_key=f"delivery:cashback:{carrinho.carrinho_id}",
            )
        )
        novo = replace(
            carrinho,
            cashback_reservado=reservado,
            versao=carrinho.versao + 1,
        )
        return self.carrinhos.salvar_cas(novo, expected_version=expected_version)

    def _revalidar_fechamento(
        self,
        *,
        carrinho: CarrinhoDelivery,
        catalogo: Iterable[ProdutoDelivery],
        areas: Iterable[AreaEntrega],
    ) -> None:
        if not carrinho.itens:
            raise ErroDelivery("carrinho_vazio")
        if carrinho.endereco is None or carrinho.cotacao is None:
            raise ErroDelivery("entrega_nao_cotada")
        produtos = _catalogo_por_id(
            catalogo,
            tenant_id=carrinho.tenant_id,
            unidade_id=carrinho.unidade_id,
        )
        for item in carrinho.itens:
            atual = produtos.get(item.produto_id)
            if atual is None:
                raise ErroDelivery("produto_indisponivel_reconfirmacao")
            if Decimal(item.quantidade) > atual.estoque_disponivel:
                raise ErroDelivery("estoque_alterado_reconfirmacao")
            if atual.preco != item.preco_unitario or atual.versao != item.produto_versao:
                raise ErroDelivery("catalogo_alterado_reconfirmacao")
        area = _area_para_cep(
            areas,
            tenant_id=carrinho.tenant_id,
            unidade_id=carrinho.unidade_id,
            cep=carrinho.endereco.cep,
        )
        if (
            area.area_id != carrinho.cotacao.area_id
            or area.versao != carrinho.cotacao.versao_area
            or area.taxa != carrinho.cotacao.taxa
            or area.sla_minutos != carrinho.cotacao.sla_minutos
            or area.sla_maxutos != carrinho.cotacao.sla_maxutos
        ):
            raise ErroDelivery("cotacao_alterada_reconfirmacao")
        self.promocoes.validar_reservas(carrinho)

    def confirmar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        carrinho_id: str,
        expected_version: int,
        metodo_pagamento: MetodoPagamento,
        idempotency_key: str,
        catalogo: Iterable[ProdutoDelivery],
        areas: Iterable[AreaEntrega],
    ) -> ResultadoConfirmacaoDelivery:
        if not idempotency_key.strip():
            raise ErroDelivery("idempotency_key_obrigatoria")
        carrinho = self._carrinho(
            tenant_id=tenant_id, unidade_id=unidade_id, carrinho_id=carrinho_id
        )
        if carrinho.status is StatusCarrinhoDelivery.CONFIRMADO:
            if carrinho.idempotency_confirmacao != idempotency_key or not carrinho.pedido_id:
                raise ErroDelivery("carrinho_ja_confirmado")
            pedido_existente = self.pedidos.obter(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                pedido_id=carrinho.pedido_id,
            )
            if pedido_existente is None:
                raise ErroDelivery("pedido_confirmado_inconsistente")
            return ResultadoConfirmacaoDelivery(
                pedido=pedido_existente, idempotente=True
            )

        retomada = carrinho.status is StatusCarrinhoDelivery.CONFIRMACAO_EM_ANDAMENTO
        if retomada:
            if carrinho.idempotency_confirmacao != idempotency_key or not carrinho.pedido_id:
                raise ErroDelivery("confirmacao_em_andamento_por_outro_comando")
            reivindicado = carrinho
        else:
            self._aberto(carrinho)
            if carrinho.versao != expected_version:
                raise ErroDelivery("conflito_concorrencia")
            if metodo_pagamento not in {
                MetodoPagamento.PIX,
                MetodoPagamento.CARTAO_CREDITO,
                MetodoPagamento.CARTAO_DEBITO,
                MetodoPagamento.PAGAMENTO_NA_ENTREGA,
            }:
                raise ErroDelivery("metodo_pagamento_delivery_nao_suportado")
            self._revalidar_fechamento(
                carrinho=carrinho, catalogo=catalogo, areas=areas
            )
            pedido_id = _id("ped", f"{tenant_id}:{unidade_id}:{idempotency_key}")
            reivindicado = replace(
                carrinho,
                status=StatusCarrinhoDelivery.CONFIRMACAO_EM_ANDAMENTO,
                pedido_id=pedido_id,
                idempotency_confirmacao=idempotency_key,
                versao=carrinho.versao + 1,
            )
            reivindicado = self.carrinhos.salvar_cas(
                reivindicado, expected_version=expected_version
            )

        self._revalidar_fechamento(
            carrinho=reivindicado, catalogo=catalogo, areas=areas
        )
        pedido_id = reivindicado.pedido_id
        endereco = reivindicado.endereco
        cotacao = reivindicado.cotacao
        if pedido_id is None or endereco is None or cotacao is None:
            raise ErroDelivery("confirmacao_inconsistente")
        if metodo_pagamento not in {
            MetodoPagamento.PIX,
            MetodoPagamento.CARTAO_CREDITO,
            MetodoPagamento.CARTAO_DEBITO,
            MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        }:
            raise ErroDelivery("metodo_pagamento_delivery_nao_suportado")

        entrega_id = self.entregas.criar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            pedido_id=pedido_id,
            endereco_id=endereco.endereco_id,
            idempotency_key=f"delivery:entrega:{idempotency_key}",
        )
        pagamento = self.pagamentos.criar_obrigacao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            pedido_id=pedido_id,
            valor=str(reivindicado.total),
            metodo=metodo_pagamento,
            idempotency_key=f"delivery:pagamento:{idempotency_key}",
        )
        pedido_novo = PedidoDelivery(
            pedido_id=pedido_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_ref=reivindicado.cliente_ref,
            carrinho_id=reivindicado.carrinho_id,
            itens=reivindicado.itens,
            endereco=endereco,
            cotacao=cotacao,
            desconto_cupom=reivindicado.desconto_cupom,
            cashback_usado=reivindicado.cashback_reservado,
            total=reivindicado.total,
            pagamento=pagamento,
            entrega_id=entrega_id,
        )
        pedido, idempotente = self.pedidos.registrar(
            pedido=pedido_novo,
            idempotency_key=f"delivery:pedido:{idempotency_key}",
        )
        if reivindicado.status is not StatusCarrinhoDelivery.CONFIRMADO:
            confirmado = replace(
                reivindicado,
                status=StatusCarrinhoDelivery.CONFIRMADO,
                versao=reivindicado.versao + 1,
            )
            self.carrinhos.salvar_cas(
                confirmado, expected_version=reivindicado.versao
            )
        self.promocoes.confirmar_reservas(
            carrinho=reivindicado, pedido_id=pedido.pedido_id
        )
        return ResultadoConfirmacaoDelivery(
            pedido=pedido, idempotente=(idempotente or retomada)
        )

    def acompanhar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_ref: str,
        pedido_id: str,
    ) -> tuple[EventoTracking, ...]:
        pedido = self.pedidos.obter(
            tenant_id=tenant_id, unidade_id=unidade_id, pedido_id=pedido_id
        )
        if pedido is None or pedido.cliente_ref != cliente_ref:
            raise ErroDelivery("recurso_indisponivel")
        return self.entregas.timeline(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            entrega_id=pedido.entrega_id,
        )

    def cancelar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_ref: str,
        pedido_id: str,
        estagio: EstagioCancelamento,
        motivo: str,
        idempotency_key: str,
    ) -> ResultadoCancelamentoDelivery:
        pedido = self.pedidos.obter(
            tenant_id=tenant_id, unidade_id=unidade_id, pedido_id=pedido_id
        )
        if pedido is None or pedido.cliente_ref != cliente_ref:
            raise ErroDelivery("recurso_indisponivel")
        if not motivo.strip() or not idempotency_key.strip():
            raise ErroDelivery("motivo_e_idempotencia_obrigatorios")
        if pedido.status is PedidoStatus.CANCELADO:
            estorno = (
                pedido.total
                if pedido.pagamento.status
                in {PagamentoStatus.PAGO, PagamentoStatus.ESTORNADO}
                else Decimal("0")
            )
            return ResultadoCancelamentoDelivery(
                pedido=pedido,
                estagio=estagio,
                estorno_previsto=estorno,
                desperdicio_estimado=(
                    Decimal("0")
                    if estagio is EstagioCancelamento.ANTES_PRODUCAO
                    else sum(
                        (i.custo_estimado for i in pedido.itens),
                        start=Decimal("0"),
                    )
                ),
                cashback_restaurado=pedido.cashback_usado,
                cupom_liberado=bool(pedido.desconto_cupom),
                idempotente=True,
            )
        if estagio is EstagioCancelamento.ENTREGUE:
            raise ErroDelivery("pedido_entregue_nao_cancelavel")
        timeline = self.entregas.timeline(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            entrega_id=pedido.entrega_id,
        )
        if timeline and timeline[-1].status is StatusEntrega.ENTREGUE:
            raise ErroDelivery("pedido_entregue_nao_cancelavel")
        status_pagamento = self.pagamentos.consultar(
            tenant_id=tenant_id, unidade_id=unidade_id, pedido_id=pedido_id
        ).status
        estorno_previsto = (
            pedido.total if status_pagamento is PagamentoStatus.PAGO else Decimal("0")
        )
        status_final = self.pagamentos.cancelar_ou_estornar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            pedido_id=pedido_id,
            valor=str(pedido.total),
            idempotency_key=f"delivery:cancelamento:pagamento:{idempotency_key}",
        )
        self.entregas.cancelar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            entrega_id=pedido.entrega_id,
            motivo=motivo,
            idempotency_key=f"delivery:cancelamento:entrega:{idempotency_key}",
        )
        carrinho = self._carrinho(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            carrinho_id=pedido.carrinho_id,
        )
        cashback_restaurado, cupom_liberado = self.promocoes.estornar_reservas(
            carrinho=carrinho, pedido_id=pedido_id
        )
        cancelado = replace(
            pedido,
            status=PedidoStatus.CANCELADO,
            pagamento=replace(pedido.pagamento, status=status_final),
            versao=pedido.versao + 1,
            cancelado_em=datetime.now(timezone.utc),
        )
        cancelado, idem = self.pedidos.cancelar(
            pedido=cancelado,
            idempotency_key=f"delivery:cancelamento:pedido:{idempotency_key}",
        )
        desperdicio = (
            Decimal("0")
            if estagio is EstagioCancelamento.ANTES_PRODUCAO
            else sum((i.custo_estimado for i in pedido.itens), start=Decimal("0"))
        )
        return ResultadoCancelamentoDelivery(
            pedido=cancelado,
            estagio=estagio,
            estorno_previsto=estorno_previsto,
            desperdicio_estimado=desperdicio,
            cashback_restaurado=moeda(cashback_restaurado),
            cupom_liberado=cupom_liberado,
            idempotente=idem,
        )

    def repetir(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_ref: str,
        pedido_id: str,
        novo_carrinho_id: str,
        catalogo: Iterable[ProdutoDelivery],
        areas: Iterable[AreaEntrega],
    ) -> CarrinhoDelivery:
        anterior = self.pedidos.obter(
            tenant_id=tenant_id, unidade_id=unidade_id, pedido_id=pedido_id
        )
        if anterior is None or anterior.cliente_ref != cliente_ref:
            raise ErroDelivery("recurso_indisponivel")
        atual = _catalogo_por_id(
            catalogo, tenant_id=tenant_id, unidade_id=unidade_id
        )
        novo = self.abrir_carrinho(
            carrinho_id=novo_carrinho_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_ref=cliente_ref,
        )
        for item in anterior.itens:
            produto = atual.get(item.produto_id)
            if produto is None or Decimal(item.quantidade) > produto.estoque_disponivel:
                raise ErroDelivery("produto_indisponivel_repeticao")
            novo = self.adicionar_item(
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                carrinho_id=novo.carrinho_id,
                produto_id=produto.produto_id,
                quantidade=item.quantidade,
                expected_version=novo.versao,
                catalogo=atual.values(),
            )
        endereco = anterior.endereco
        novo = self.definir_endereco(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            carrinho_id=novo.carrinho_id,
            endereco=endereco,
            expected_version=novo.versao,
            areas=areas,
        )
        return novo
