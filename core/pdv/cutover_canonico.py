"""Ponte segura entre o PDV legado e o núcleo canônico da V1.

O bootstrap de estoque ocorre uma única vez por insumo legado. Depois disso,
qualquer diferença entre saldo legado e ledger canônico bloqueia o canary: não
existe sincronização silenciosa capaz de esconder dupla fonte de verdade.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from application.checkout import ComandoCheckoutV1
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.ids import (
    ClienteId,
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import ItemPedido, Pedido
from core.dominio.tipos import QuantidadeItem
from core.estoque.modelos import ItemSnapshotFicha, SnapshotFichaEstoque, TipoMovimento
from core.estoque.servicos import registrar_movimento
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import RecursosTransacionaisV1

from .adaptadores_sqlalchemy import LegacyPDVSQLAlchemyAdapter
from .modelos import (
    EntradaPDV,
    id_cliente_legado,
    id_insumo_legado,
    id_produto_legado,
    mapear_metodo,
)


class DivergenciaEstoqueCutover(RuntimeError):
    """Ledger canônico e estoque legado deixaram de representar o mesmo saldo físico."""


def _id_deterministico(chave: str) -> str:
    return str(uuid5(NAMESPACE_URL, chave))


def montar_pedido_pdv(
    *, entrada: EntradaPDV, contexto: ContextoExecucao, instante: datetime
) -> Pedido:
    chave = entrada.idempotency_key
    pedido_id = _id_deterministico(
        f"{contexto.tenant_id}:{contexto.unidade_id}:{chave}:pedido"
    )
    tenant = TenantId(contexto.tenant_id)
    unidade = UnidadeId(contexto.unidade_id)
    item = ItemPedido(
        id=PedidoItemId(_id_deterministico(f"{pedido_id}:item:1")),
        tenant_id=tenant,
        unidade_id=unidade,
        produto_id=ProdutoId(id_produto_legado(entrada.produto_id)),
        nome_produto=entrada.produto_nome,
        quantidade=QuantidadeItem(entrada.quantidade),
        preco_unitario=entrada.preco_unitario,
        subtotal=entrada.subtotal,
    )
    return Pedido(
        id=PedidoId(pedido_id),
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.PDV,
        canal=CanalAtendimento.PDV,
        status=PedidoStatus.RASCUNHO,
        cliente_id=ClienteId(id_cliente_legado(entrada.cliente_id))
        if entrada.cliente_id is not None
        else None,
        criado_em=instante,
        atualizado_em=instante,
        versao=1,
        correlation_id=CorrelationId(contexto.correlation_id),
        idempotency_key=IdempotencyKey(f"{chave}:pedido"),
        subtotal=entrada.subtotal,
        descontos=entrada.desconto_cashback,
        taxas=Dinheiro(0),
        total=entrada.total,
        itens=(item,),
        observacoes=(),
    )


def preparar_snapshot_estoque_pdv(
    *,
    entrada: EntradaPDV,
    contexto: ContextoExecucao,
    pedido: Pedido,
    recursos: RecursosTransacionaisV1,
    legado: LegacyPDVSQLAlchemyAdapter,
) -> tuple[SnapshotFichaEstoque, list[tuple[object, Decimal]]]:
    """Valida/ancora o saldo do cutover e cria snapshot imutável da receita."""

    consumos = legado.validar_estoque(entrada)
    itens: list[ItemSnapshotFicha] = []
    for insumo, necessario in consumos:
        insumo_id = id_insumo_legado(getattr(insumo, "id"))
        saldo_legado = Decimal(str(getattr(insumo, "saldo_atual", 0) or 0))
        saldo = recursos.estoque.consultar_saldo(
            contexto.tenant_id, contexto.unidade_id, insumo_id
        )
        if saldo.versao == 0:
            bootstrap = registrar_movimento(
                contexto=contexto,
                repositorio=recursos.estoque,
                insumo_id=insumo_id,
                tipo=TipoMovimento.ENTRADA,
                quantidade_movimento=saldo_legado,
                unidade_medida=str(
                    getattr(insumo, "unidade_medida", None)
                    or getattr(insumo, "unidade", None)
                    or "un"
                ),
                origem_tipo="pdv_cutover",
                origem_id=f"bootstrap:{insumo_id}",
                origem_versao=1,
                idempotency_key=f"pdv:cutover:bootstrap:{insumo_id}",
                motivo="bootstrap controlado do estoque legado para ledger canônico",
            )
            recursos.registrar_efeitos(
                eventos=bootstrap.eventos, auditorias=bootstrap.auditorias
            )
            saldo = recursos.estoque.consultar_saldo(
                contexto.tenant_id, contexto.unidade_id, insumo_id
            )
        if saldo.saldo_fisico != saldo_legado:
            raise DivergenciaEstoqueCutover(
                f"estoque_divergente:{insumo_id}:canonico={saldo.saldo_fisico}:legado={saldo_legado}"
            )
        unidade_medida = str(
            getattr(insumo, "unidade_medida", None)
            or getattr(insumo, "unidade", None)
            or "un"
        )
        itens.append(
            ItemSnapshotFicha(
                produto_id=str(pedido.itens[0].produto_id),
                item_pedido_id=str(pedido.itens[0].id),
                insumo_id=insumo_id,
                quantidade_por_unidade=necessario / Decimal(entrada.quantidade),
                quantidade_total=necessario,
                unidade_medida=unidade_medida,
            )
        )
    return (
        SnapshotFichaEstoque(
            pedido_id=str(pedido.id),
            versao_ficha=f"pdv-legado:{entrada.produto_id}",
            capturado_em=pedido.criado_em,
            itens=tuple(itens),
        ),
        consumos,
    )


def montar_checkout_pdv(
    *,
    entrada: EntradaPDV,
    contexto: ContextoExecucao,
    instante: datetime,
    recursos: RecursosTransacionaisV1,
    legado: LegacyPDVSQLAlchemyAdapter,
) -> tuple[ComandoCheckoutV1, list[tuple[object, Decimal]]]:
    pedido = montar_pedido_pdv(entrada=entrada, contexto=contexto, instante=instante)
    snapshot, consumos = preparar_snapshot_estoque_pdv(
        entrada=entrada,
        contexto=contexto,
        pedido=pedido,
        recursos=recursos,
        legado=legado,
    )
    return (
        ComandoCheckoutV1(
            pedido=pedido,
            timestamp=instante,
            pagamento_id=_id_deterministico(f"{entrada.idempotency_key}:pagamento"),
            metodo_pagamento=mapear_metodo(entrada.forma_pagamento),
            snapshot_estoque=snapshot,
            provedor_pagamento="sandbox" if entrada.pix_sandbox else None,
        ),
        consumos,
    )
