"""Boundary comercial F11-D para benefícios do Delivery Próprio no Checkout V1.

O domínio ``core.delivery`` continua responsável por calcular/reservar cupom e
cashback. Esta camada decide se esses valores podem atravessar a fronteira
comercial e, quando elegíveis, os incorpora ao Pedido antes de chamar o checkout
canônico. Nenhum commit é aberto ou encerrado aqui.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from decimal import Decimal

from application.checkout import (
    ComandoCheckoutV1,
    ResultadoCheckoutV1,
    executar_checkout_em_transacao,
)
from application.delivery_contexto_comercial import ContextoDeliveryComercialV1
from core.delivery.modelos import CarrinhoDelivery, moeda
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import OrigemPedido
from core.dominio.ids import CausationId, EventoId, IdempotencyKey, TenantId, UnidadeId
from core.eventos.modelos import EnvelopeMensagem
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import RecursosTransacionaisV1


class CheckoutDeliveryComercialInvalido(ValueError):
    """Invariante da convergência comercial do Delivery foi violada."""


class BeneficioDeliveryObrigatorioIndisponivel(CheckoutDeliveryComercialInvalido):
    """Política explicitamente obrigatória não pôde ser satisfeita."""


@dataclass(frozen=True)
class PoliticaBeneficiosDeliveryV1:
    ativa: bool = True
    disponivel: bool = True
    obrigatoria: bool = False
    metodos_elegiveis: frozenset[MetodoPagamento] = frozenset(
        {
            MetodoPagamento.PIX,
            MetodoPagamento.CARTAO_CREDITO,
            MetodoPagamento.CARTAO_DEBITO,
            MetodoPagamento.PAGAMENTO_NA_ENTREGA,
        }
    )


@dataclass(frozen=True)
class DecisaoBeneficiosDeliveryV1:
    aceito: bool
    motivo: str
    origem_pedido: str
    metodo_pagamento: str | None
    desconto_cupom: Decimal
    cashback: Decimal
    beneficio_total: Decimal
    total_antes: Decimal
    total_depois: Decimal


@dataclass(frozen=True)
class CheckoutDeliveryComercialV1:
    decisao: DecisaoBeneficiosDeliveryV1
    checkout: ResultadoCheckoutV1


def _falha_ou_neutro(
    *,
    politica: PoliticaBeneficiosDeliveryV1,
    motivo: str,
    comando: ComandoCheckoutV1,
    carrinho: CarrinhoDelivery,
) -> tuple[ComandoCheckoutV1, DecisaoBeneficiosDeliveryV1]:
    beneficio = moeda(carrinho.desconto_cupom + carrinho.cashback_reservado)
    if politica.obrigatoria and beneficio > 0:
        raise BeneficioDeliveryObrigatorioIndisponivel(motivo)
    total = comando.pedido.total.valor
    return comando, DecisaoBeneficiosDeliveryV1(
        aceito=False,
        motivo=motivo,
        origem_pedido=str(comando.pedido.origem),
        metodo_pagamento=(
            comando.metodo_pagamento.value if comando.metodo_pagamento else None
        ),
        desconto_cupom=carrinho.desconto_cupom,
        cashback=carrinho.cashback_reservado,
        beneficio_total=beneficio,
        total_antes=total,
        total_depois=total,
    )


def preparar_checkout_com_beneficios_delivery(
    *,
    comando: ComandoCheckoutV1,
    contexto_delivery: ContextoDeliveryComercialV1,
    carrinho: CarrinhoDelivery,
    politica: PoliticaBeneficiosDeliveryV1 | None = None,
) -> tuple[ComandoCheckoutV1, DecisaoBeneficiosDeliveryV1]:
    """Aplica somente benefícios já resolvidos pelo domínio Delivery.

    O caminho neutro preserva integralmente o comando original. Bloqueio só ocorre
    quando a política recebida declarar o benefício como obrigatório.
    """

    politica = politica or PoliticaBeneficiosDeliveryV1()
    pedido = comando.pedido
    escopo = contexto_delivery.contexto
    if (
        str(pedido.tenant_id) != escopo.tenant_id
        or str(pedido.unidade_id) != escopo.unidade_id
        or carrinho.tenant_id != escopo.tenant_id
        or carrinho.unidade_id != escopo.unidade_id
    ):
        raise CheckoutDeliveryComercialInvalido("escopo_delivery_checkout_invalido")
    if carrinho.cliente_ref != contexto_delivery.cliente.cliente_id:
        raise CheckoutDeliveryComercialInvalido("cliente_delivery_checkout_invalido")
    if pedido.cliente_id is not None and str(pedido.cliente_id) != carrinho.cliente_ref:
        raise CheckoutDeliveryComercialInvalido("cliente_pedido_delivery_divergente")

    beneficio = moeda(carrinho.desconto_cupom + carrinho.cashback_reservado)
    if beneficio == 0:
        return _falha_ou_neutro(
            politica=politica,
            motivo="sem_beneficio_reservado",
            comando=comando,
            carrinho=carrinho,
        )
    if not politica.disponivel:
        return _falha_ou_neutro(
            politica=politica,
            motivo="beneficios_indisponiveis",
            comando=comando,
            carrinho=carrinho,
        )
    if not politica.ativa:
        return _falha_ou_neutro(
            politica=politica,
            motivo="beneficios_inativos",
            comando=comando,
            carrinho=carrinho,
        )
    if pedido.origem is not OrigemPedido.DELIVERY_PROPRIO:
        return _falha_ou_neutro(
            politica=politica,
            motivo="origem_nao_elegivel",
            comando=comando,
            carrinho=carrinho,
        )
    if comando.metodo_pagamento not in politica.metodos_elegiveis:
        return _falha_ou_neutro(
            politica=politica,
            motivo="metodo_pagamento_nao_elegivel",
            comando=comando,
            carrinho=carrinho,
        )
    if beneficio > pedido.total.valor:
        raise CheckoutDeliveryComercialInvalido("beneficio_superior_total_pedido")

    total_antes = pedido.total.valor
    descontos = Dinheiro(
        pedido.descontos.valor + beneficio,
        pedido.descontos.moeda,
    )
    total = Dinheiro(total_antes - beneficio, pedido.total.moeda)
    pedido_beneficiado = replace(pedido, descontos=descontos, total=total)
    comando_beneficiado = replace(comando, pedido=pedido_beneficiado)
    if total.valor == 0:
        comando_beneficiado = replace(
            comando_beneficiado,
            pagamento_id=None,
            metodo_pagamento=None,
            provedor_pagamento=None,
            recebimento_posterior=False,
        )

    return comando_beneficiado, DecisaoBeneficiosDeliveryV1(
        aceito=True,
        motivo="beneficio_aplicado",
        origem_pedido=str(pedido.origem),
        metodo_pagamento=(
            comando.metodo_pagamento.value if comando.metodo_pagamento else None
        ),
        desconto_cupom=carrinho.desconto_cupom,
        cashback=carrinho.cashback_reservado,
        beneficio_total=beneficio,
        total_antes=total_antes,
        total_depois=total.valor,
    )


def _id_deterministico(prefixo: str, raiz: str) -> str:
    digest = hashlib.sha256(raiz.encode("utf-8")).hexdigest()[:24]
    return f"{prefixo}-{digest}"


def _registrar_decisao(
    *,
    decisao: DecisaoBeneficiosDeliveryV1,
    comando: ComandoCheckoutV1,
    contexto: ContextoExecucao,
    recursos: RecursosTransacionaisV1,
) -> None:
    pedido_id = str(comando.pedido.id)
    raiz = str(comando.pedido.idempotency_key)
    chave = f"{raiz}:beneficio_delivery"
    evento = EnvelopeMensagem(
        event_id=EventoId(_id_deterministico("evt", chave)),
        event_type="delivery.beneficio.checkout.avaliado.v1",
        aggregate_id=pedido_id,
        aggregate_type="Pedido",
        tenant_id=TenantId(contexto.tenant_id),
        unidade_id=UnidadeId(contexto.unidade_id),
        correlation_id=comando.pedido.correlation_id,
        causation_id=(CausationId(contexto.causation_id) if contexto.causation_id else None),
        idempotency_key=IdempotencyKey(chave),
        occurred_at=comando.timestamp,
        payload={
            "aceito": decisao.aceito,
            "motivo": decisao.motivo,
            "origem_pedido": decisao.origem_pedido,
            "metodo_pagamento": decisao.metodo_pagamento,
            "beneficio_total": str(decisao.beneficio_total),
            "desconto_cupom": str(decisao.desconto_cupom),
            "cashback": str(decisao.cashback),
            "total_antes": str(decisao.total_antes),
            "total_depois": str(decisao.total_depois),
        },
    )
    papel = next(iter(sorted(contexto.papeis, key=str)), None)
    auditoria = EventoAuditoria(
        audit_id=_id_deterministico("aud", chave),
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        usuario_id=contexto.usuario_id,
        papel_efetivo=papel,
        acao="avaliar_beneficio_delivery_checkout",
        recurso_tipo="Pedido",
        recurso_id=pedido_id,
        resultado="permitido" if decisao.aceito else "neutro",
        motivo=decisao.motivo,
        correlation_id=contexto.correlation_id,
        timestamp=comando.timestamp,
        origem=contexto.origem,
        politica="f11-d-delivery-beneficios-v1",
        causation_id=contexto.causation_id,
        metadata=sanitizar_metadata(
            {
                "origem_pedido": decisao.origem_pedido,
                "metodo_pagamento": decisao.metodo_pagamento,
                "beneficio_aplicado": str(decisao.beneficio_total),
            }
        ),
    )
    recursos.registrar_efeitos(eventos=(evento,), auditorias=(auditoria,))


def executar_checkout_delivery_comercial_em_transacao(
    *,
    comando: ComandoCheckoutV1,
    contexto: ContextoExecucao,
    contexto_delivery: ContextoDeliveryComercialV1,
    carrinho: CarrinhoDelivery,
    recursos: RecursosTransacionaisV1,
    politica: PoliticaBeneficiosDeliveryV1 | None = None,
) -> CheckoutDeliveryComercialV1:
    """Converge benefícios e executa o Checkout V1 dentro da UoW do chamador."""

    politica = politica or PoliticaBeneficiosDeliveryV1()
    comando_final, decisao = preparar_checkout_com_beneficios_delivery(
        comando=comando,
        contexto_delivery=contexto_delivery,
        carrinho=carrinho,
        politica=politica,
    )
    if (
        contexto.tenant_id != contexto_delivery.contexto.tenant_id
        or contexto.unidade_id != contexto_delivery.contexto.unidade_id
    ):
        raise CheckoutDeliveryComercialInvalido("contextos_comerciais_divergentes")

    _registrar_decisao(
        decisao=decisao,
        comando=comando,
        contexto=contexto,
        recursos=recursos,
    )
    checkout = executar_checkout_em_transacao(
        comando=comando_final,
        contexto=contexto,
        recursos=recursos,
    )
    return CheckoutDeliveryComercialV1(decisao=decisao, checkout=checkout)
