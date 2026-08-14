"""Checkout canônico da V1.

Canais como PDV, Assistente de Atendimento, Salão, Delivery e marketplaces devem entrar por esta
fronteira. Pedido/Pagamento preservam a identidade do operador/canal, enquanto
efeitos automáticos de estoque podem usar uma identidade técnica auditável.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from core.dominio.enums import PedidoStatus
from core.dominio.ids import IdempotencyKey
from core.dominio.pedidos import Pedido
from core.estoque.modelos import ResultadoReserva, SnapshotFichaEstoque
from core.estoque.servicos import reservar_estoque
from core.pagamentos.modelos import MetodoPagamento, ResultadoPagamento
from core.pagamentos.servicos import criar_obrigacao_pagamento
from core.pedidos.servicos import (
    ResultadoPedidoAutoritativo,
    registrar_novo_pedido,
    transicionar_pedido,
)
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import RecursosTransacionaisV1, UnitOfWorkV1


class CheckoutInvalido(ValueError):
    """Comando de checkout inconsistente antes de tocar persistência."""


@dataclass(frozen=True, kw_only=True)
class ComandoCheckoutV1:
    pedido: Pedido
    timestamp: datetime
    pagamento_id: str | None
    metodo_pagamento: MetodoPagamento | None
    snapshot_estoque: SnapshotFichaEstoque | None = None
    provedor_pagamento: str | None = None
    recebimento_posterior: bool = False


@dataclass(frozen=True)
class ResultadoCheckoutV1:
    pedido: ResultadoPedidoAutoritativo
    pagamento: ResultadoPagamento | None
    reserva: ResultadoReserva | None
    aguardando_confirmacao: ResultadoPedidoAutoritativo


def _validar(comando: ComandoCheckoutV1, contexto: ContextoExecucao) -> None:
    pedido = comando.pedido
    if pedido.status is not PedidoStatus.RASCUNHO:
        raise CheckoutInvalido("checkout exige pedido em rascunho")
    if (
        str(pedido.tenant_id) != contexto.tenant_id
        or str(pedido.unidade_id) != contexto.unidade_id
    ):
        raise CheckoutInvalido("pedido fora do tenant/unidade do checkout")
    if pedido.total.valor < 0:
        raise CheckoutInvalido("total do pedido não pode ser negativo")
    if (
        comando.snapshot_estoque is not None
        and comando.snapshot_estoque.pedido_id != str(pedido.id)
    ):
        raise CheckoutInvalido("snapshot de estoque pertence a outro pedido")
    if pedido.total.valor > 0 and (
        not comando.pagamento_id or comando.metodo_pagamento is None
    ):
        raise CheckoutInvalido("pedido com valor exige obrigação de pagamento")
    if pedido.total.valor == 0 and (
        comando.pagamento_id or comando.metodo_pagamento is not None
    ):
        raise CheckoutInvalido("pedido zerado não deve criar obrigação financeira")


def _validar_contexto_estoque(
    *, contexto: ContextoExecucao, contexto_estoque: ContextoExecucao
) -> None:
    if (
        contexto_estoque.tenant_id != contexto.tenant_id
        or contexto_estoque.unidade_id != contexto.unidade_id
        or contexto_estoque.correlation_id != contexto.correlation_id
    ):
        raise CheckoutInvalido("contexto automático de estoque fora do checkout")


def executar_checkout_em_transacao(
    *,
    comando: ComandoCheckoutV1,
    contexto: ContextoExecucao,
    recursos: RecursosTransacionaisV1,
    contexto_estoque: ContextoExecucao | None = None,
) -> ResultadoCheckoutV1:
    """Executa o checkout na Session recebida; o chamador continua dono do commit."""

    _validar(comando, contexto)
    contexto_estoque = contexto_estoque or contexto
    _validar_contexto_estoque(contexto=contexto, contexto_estoque=contexto_estoque)
    pedido = comando.pedido
    raiz = str(pedido.idempotency_key)

    criado = registrar_novo_pedido(
        pedido=pedido,
        contexto=contexto,
        repositorio=recursos.pedidos,
        outbox=recursos.outbox,
        auditoria=recursos.auditoria,
    )

    pagamento: ResultadoPagamento | None = None
    if pedido.total.valor > 0:
        pagamento_id = comando.pagamento_id
        metodo_pagamento = comando.metodo_pagamento
        if pagamento_id is None or metodo_pagamento is None:
            raise CheckoutInvalido("pedido com valor exige obrigação de pagamento")
        pagamento = criar_obrigacao_pagamento(
            contexto=contexto,
            repositorio=recursos.pagamentos,
            pagamento_id=pagamento_id,
            pedido_id=str(pedido.id),
            valor_previsto=pedido.total,
            metodo=metodo_pagamento,
            idempotency_key=f"{raiz}:pagamento",
            timestamp=comando.timestamp,
            provedor=comando.provedor_pagamento,
            recebimento_posterior=comando.recebimento_posterior,
        )
        if not pagamento.idempotente:
            recursos.registrar_efeitos(
                eventos=pagamento.eventos,
                auditorias=pagamento.auditorias,
            )

    reserva: ResultadoReserva | None = None
    if comando.snapshot_estoque is not None:
        reserva = reservar_estoque(
            contexto=contexto_estoque,
            repositorio=recursos.estoque,
            pedido_id=str(pedido.id),
            pedido_version=pedido.versao,
            snapshot_ficha=comando.snapshot_estoque,
            idempotency_key=f"{raiz}:estoque",
        )
        if not reserva.idempotente:
            recursos.registrar_efeitos(
                eventos=reserva.eventos,
                auditorias=reserva.auditorias,
            )

    aguardando = transicionar_pedido(
        tenant_id=pedido.tenant_id,
        unidade_id=pedido.unidade_id,
        pedido_id=pedido.id,
        destino=PedidoStatus.AGUARDANDO_CONFIRMACAO,
        versao_esperada=pedido.versao,
        idempotency_key=IdempotencyKey(f"{raiz}:aguardando_confirmacao"),
        contexto=contexto,
        repositorio=recursos.pedidos,
        outbox=recursos.outbox,
        auditoria=recursos.auditoria,
        timestamp=comando.timestamp,
        precondicoes={"itens_validos": bool(pedido.itens), "precos_calculados": True},
        metadata={
            "pagamento_criado": pagamento is not None,
            "estoque_reservado": reserva is not None,
        },
    )
    return ResultadoCheckoutV1(criado, pagamento, reserva, aguardando)


def executar_checkout_v1(
    *,
    comando: ComandoCheckoutV1,
    contexto: ContextoExecucao,
    session_factory: Callable[[], Session],
    contexto_estoque: ContextoExecucao | None = None,
) -> ResultadoCheckoutV1:
    """Registra checkout inteiro ou nada; replays usam as mesmas chaves derivadas."""

    with UnitOfWorkV1(session_factory) as uow:
        resultado = executar_checkout_em_transacao(
            comando=comando,
            contexto=contexto,
            recursos=uow.recursos,
            contexto_estoque=contexto_estoque,
        )
        uow.commit()
        return resultado
