"""Consulta operacional de itens canônicos ainda não roteados ao KDS."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from core.kds.modelos_orm import ProducaoItemORM
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.seguranca import AutorizarAcao, ContextoExecucao, Permissao


@dataclass(frozen=True)
class ItemPendenteRoteamentoKDS:
    pedido_id: str
    pedido_item_id: str
    nome_produto: str
    quantidade: Decimal
    status_pedido: str


def listar_itens_pendentes(
    session: Session, contexto: ContextoExecucao
) -> tuple[ItemPendenteRoteamentoKDS, ...]:
    decisao = AutorizarAcao().executar(
        contexto=contexto,
        permissao=Permissao.PRODUCAO_ATUALIZAR,
        recurso="roteamento_kds",
        tenant_recurso=contexto.tenant_id,
        unidade_recurso=contexto.unidade_id,
    )
    if not decisao.autorizado:
        return ()

    vinculo = and_(
        PedidoORM.tenant_id == ItemPedidoORM.tenant_id,
        PedidoORM.unidade_id == ItemPedidoORM.unidade_id,
        PedidoORM.id == ItemPedidoORM.pedido_id,
    )
    ja_roteado = (
        select(ProducaoItemORM.id)
        .where(
            ProducaoItemORM.tenant_id == ItemPedidoORM.tenant_id,
            ProducaoItemORM.unidade_id == ItemPedidoORM.unidade_id,
            ProducaoItemORM.pedido_id == ItemPedidoORM.pedido_id,
            ProducaoItemORM.pedido_item_id == ItemPedidoORM.id,
        )
        .exists()
    )
    rows = session.execute(
        select(ItemPedidoORM, PedidoORM.status)
        .join(PedidoORM, vinculo)
        .where(
            PedidoORM.tenant_id == contexto.tenant_id,
            PedidoORM.unidade_id == contexto.unidade_id,
            PedidoORM.status.in_(("confirmado", "enviado_producao", "em_preparo")),
            ~ja_roteado,
        )
        .order_by(PedidoORM.criado_em, ItemPedidoORM.ordem, ItemPedidoORM.id)
    ).all()
    return tuple(
        ItemPendenteRoteamentoKDS(
            pedido_id=item.pedido_id,
            pedido_item_id=item.id,
            nome_produto=item.nome_produto,
            quantidade=Decimal(str(item.quantidade)),
            status_pedido=status,
        )
        for item, status in rows
    )
