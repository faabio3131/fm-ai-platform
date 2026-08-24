"""Projeções legadas idempotentes após liquidação canônica do PDV."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from sqlalchemy import insert, select, update
from sqlalchemy.engine import CursorResult

from core.estoque.modelos import ReservaEstoque
from core.pdv.adaptadores_sqlalchemy import RepositorioPDVSQLAlchemy, TipoEfeitoCompat
from core.pdv.modelos import EntradaPDV
from infra.legacy_product_scope import (
    atualizar_insumo_legado,
    obter_insumo_por_id_legado,
)
from infra.legacy_schema import clientes, vendas
from infra.transacoes.uow import RecursosTransacionaisV1


class ProjecaoLegadaInvalida(RuntimeError):
    pass


def _insumo_legado_id(insumo_id: str) -> int:
    prefixo = "legacy:insumo:"
    if not insumo_id.startswith(prefixo):
        raise ProjecaoLegadaInvalida("snapshot sem insumo legado")
    try:
        return int(insumo_id.removeprefix(prefixo))
    except ValueError as exc:
        raise ProjecaoLegadaInvalida("identificador de insumo legado inválido") from exc


def projetar_legado_em_transacao(
    *,
    recursos: RecursosTransacionaisV1,
    tenant_id: str,
    unidade_id: str,
    pedido_id: str,
    entrada: EntradaPDV,
    reserva: ReservaEstoque | None,
    timestamp: datetime,
) -> str:
    session = recursos.session
    pdv = RepositorioPDVSQLAlchemy(session)

    efeito_venda = pdv.buscar_efeito(
        tenant_id, unidade_id, pedido_id, TipoEfeitoCompat.VENDA_LEGADA
    )
    if efeito_venda and efeito_venda.referencia_legada:
        venda_legada_id = efeito_venda.referencia_legada
    else:
        resultado = cast(
            CursorResult[Any],
            session.execute(
                insert(vendas).values(
                    produto_id=entrada.produto_id,
                    cliente_id=entrada.cliente_id,
                    quantidade=entrada.quantidade,
                    valor_total=float(entrada.total.valor),
                    custo_total=float(entrada.custo_total.valor),
                    forma_pagamento=entrada.forma_pagamento,
                    status_pagamento="Aprovado",
                    data_venda=timestamp.replace(tzinfo=None),
                )
            )
        )
        chave = resultado.inserted_primary_key
        if not chave or chave[0] is None:
            raise ProjecaoLegadaInvalida("venda legada sem identificador")
        venda_legada_id = str(chave[0])
        pdv.registrar_efeito(
            tenant=tenant_id,
            unidade=unidade_id,
            pedido_id=pedido_id,
            tipo=TipoEfeitoCompat.VENDA_LEGADA,
            chave=f"{entrada.idempotency_key}:legacy_sale",
            referencia=venda_legada_id,
            instante=timestamp,
        )

    if pdv.buscar_efeito(
        tenant_id, unidade_id, pedido_id, TipoEfeitoCompat.ESTOQUE_LEGADO
    ) is None:
        if reserva is not None:
            for item in reserva.snapshot.itens:
                insumo_id = _insumo_legado_id(item.insumo_id)
                insumo = obter_insumo_por_id_legado(
                    session,
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    insumo_id=insumo_id,
                    for_update=True,
                )
                if insumo is None:
                    raise ProjecaoLegadaInvalida("insumo legado não encontrado")
                atual = Decimal(str(insumo.saldo_atual or 0))
                if atual < item.quantidade_total:
                    raise ProjecaoLegadaInvalida("estoque legado divergente")
                atualizar_insumo_legado(
                    session,
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    insumo_id=insumo_id,
                    valores={
                        "saldo_atual": float(atual - item.quantidade_total),
                    },
                )
        pdv.registrar_efeito(
            tenant=tenant_id,
            unidade=unidade_id,
            pedido_id=pedido_id,
            tipo=TipoEfeitoCompat.ESTOQUE_LEGADO,
            chave=f"{entrada.idempotency_key}:legacy_stock",
            instante=timestamp,
        )

    if entrada.cliente_id is None:
        return venda_legada_id

    usado = pdv.buscar_efeito(
        tenant_id, unidade_id, pedido_id, TipoEfeitoCompat.CASHBACK_USADO
    )
    ganho = pdv.buscar_efeito(
        tenant_id, unidade_id, pedido_id, TipoEfeitoCompat.CASHBACK_GANHO
    )
    if ganho and (not entrada.usar_cashback or usado):
        return venda_legada_id

    linha = session.execute(
        select(clientes.c.saldo_cashback, clientes.c.total_gasto)
        .where(clientes.c.id == entrada.cliente_id)
        .with_for_update()
    ).first()
    if linha is None:
        raise ProjecaoLegadaInvalida("cliente legado não encontrado")

    saldo = Decimal(str(linha.saldo_cashback or 0))
    total_gasto = Decimal(str(linha.total_gasto or 0))
    if entrada.usar_cashback and usado is None:
        if saldo < entrada.desconto_cashback.valor:
            raise ProjecaoLegadaInvalida("saldo cashback legado divergente")
        saldo -= entrada.desconto_cashback.valor
        pdv.registrar_efeito(
            tenant=tenant_id,
            unidade=unidade_id,
            pedido_id=pedido_id,
            tipo=TipoEfeitoCompat.CASHBACK_USADO,
            chave=f"{entrada.idempotency_key}:cashback_use",
            instante=timestamp,
        )
    if ganho is None:
        saldo += (entrada.total.valor * Decimal("0.05")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_gasto += entrada.total.valor
        pdv.registrar_efeito(
            tenant=tenant_id,
            unidade=unidade_id,
            pedido_id=pedido_id,
            tipo=TipoEfeitoCompat.CASHBACK_GANHO,
            chave=f"{entrada.idempotency_key}:cashback_gain",
            instante=timestamp,
        )
    session.execute(
        update(clientes)
        .where(clientes.c.id == entrada.cliente_id)
        .values(
            saldo_cashback=float(saldo),
            total_gasto=float(total_gasto),
            ultima_compra=timestamp.replace(tzinfo=None),
            status="Ativo",
        )
    )
    return venda_legada_id
