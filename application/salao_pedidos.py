"""Composição transacional para lançar um Pedido canônico em uma comanda do Salão V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.dominio.enums import PedidoStatus
from core.dominio.erros import ConflitoIdempotencia
from core.dominio.ids import IdempotencyKey, PedidoId, TenantId, UnidadeId
from core.dominio.pedidos import Pedido
from core.pedidos.servicos import registrar_novo_pedido, transicionar_pedido
from core.salao import Comanda, RepositorioSalaoSQLAlchemy, ServicoSalao
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import UnitOfWorkV1


@dataclass(frozen=True)
class ResultadoLancamentoPedidoSalao:
    pedido: Pedido
    comanda: Comanda
    idempotente: bool


def _semantica_pedido(pedido: Pedido) -> tuple[object, ...]:
    return (
        str(pedido.tenant_id),
        str(pedido.unidade_id),
        pedido.origem.value,
        pedido.canal.value,
        str(pedido.subtotal.valor),
        str(pedido.descontos.valor),
        str(pedido.taxas.valor),
        str(pedido.total.valor),
        tuple(
            (
                str(item.produto_id) if item.produto_id else None,
                item.nome_produto,
                item.quantidade.valor,
                str(item.preco_unitario.valor),
                str(item.subtotal.valor),
                item.observacao,
            )
            for item in pedido.itens
        ),
    )


def lancar_pedido_salao_v1(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao,
    comanda_id: str,
    pedido: Pedido,
    expected_comanda_version: int,
    idempotency_key: str,
) -> ResultadoLancamentoPedidoSalao:
    """Cria, confirma e vincula um pedido à comanda sob uma única UoW.

    O Pedido permanece sem obrigação financeira no lançamento. A liquidação é
    responsabilidade do fluxo canônico de fechamento da comanda.
    """

    chave = idempotency_key.strip()
    if not chave:
        raise ValueError("idempotency_key_obrigatoria")

    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise RuntimeError("UnitOfWorkV1 sem Session ativa")

        criado = registrar_novo_pedido(
            pedido=pedido,
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
        )
        if criado.idempotente and _semantica_pedido(criado.pedido) != _semantica_pedido(
            pedido
        ):
            raise ConflitoIdempotencia(
                "payload divergente para a mesma idempotency_key"
            )

        aguardando = transicionar_pedido(
            tenant_id=TenantId(contexto.tenant_id),
            unidade_id=UnidadeId(contexto.unidade_id),
            pedido_id=PedidoId(str(pedido.id)),
            destino=PedidoStatus.AGUARDANDO_CONFIRMACAO,
            versao_esperada=1,
            idempotency_key=IdempotencyKey(f"{chave}:aguardando-confirmacao"),
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
            timestamp=pedido.criado_em,
            precondicoes={"itens_validos": True, "precos_calculados": True},
            motivo="itens do salão validados contra catálogo ativo e escopado",
        )
        confirmado = transicionar_pedido(
            tenant_id=TenantId(contexto.tenant_id),
            unidade_id=UnidadeId(contexto.unidade_id),
            pedido_id=PedidoId(str(pedido.id)),
            destino=PedidoStatus.CONFIRMADO,
            versao_esperada=2,
            idempotency_key=IdempotencyKey(f"{chave}:confirmado"),
            contexto=contexto,
            repositorio=uow.pedidos,
            outbox=uow.outbox,
            auditoria=uow.auditoria,
            timestamp=pedido.criado_em,
            precondicoes={"dados_confirmados": True},
            motivo="lançamento confirmado pelo operador do salão",
        )
        _ = aguardando

        comanda = ServicoSalao(
            RepositorioSalaoSQLAlchemy(uow.session),
            agora=lambda: pedido.criado_em,
        ).vincular_pedido(
            contexto,
            comanda_id=comanda_id,
            pedido_id=str(pedido.id),
            expected_version=expected_comanda_version,
            idempotency_key=f"{chave}:comanda",
        )

        uow.commit()
        return ResultadoLancamentoPedidoSalao(
            pedido=confirmado.pedido,
            comanda=comanda,
            idempotente=criado.idempotente,
        )
