"""Compatibilidade mínima do saldo legado no marco real de produção.

O ledger canônico é a autoridade. Este adapter só mantém o saldo legado
transitório alinhado quando um movimento canônico consome um insumo ancorado
como legacy:insumo:<id>. Não decide consumo e não cria segunda autoridade.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from core.estoque.modelos import MovimentoEstoque
from infra.legacy_product_scope import (
    atualizar_insumo_legado,
    obter_insumo_por_id_legado,
)


class ProjecaoEstoqueLegadoInvalida(RuntimeError):
    pass


def projetar_consumo_estoque_legado_em_transacao(
    *,
    session: Session,
    tenant_id: str,
    unidade_id: str,
    movimentos: tuple[MovimentoEstoque, ...],
) -> None:
    """Replica somente consumos canônicos já autorizados para o legado transitório."""

    prefixo = "legacy:insumo:"
    for movimento in movimentos:
        if not movimento.insumo_id.startswith(prefixo):
            continue
        try:
            insumo_id = int(movimento.insumo_id.removeprefix(prefixo))
        except ValueError as exc:
            raise ProjecaoEstoqueLegadoInvalida(
                "referencia_insumo_legado_invalida"
            ) from exc

        insumo = obter_insumo_por_id_legado(
            session,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            insumo_id=insumo_id,
            for_update=True,
        )
        if insumo is None:
            raise ProjecaoEstoqueLegadoInvalida("insumo_legado_indisponivel")

        atual = Decimal(str(insumo.saldo_atual or 0))
        if atual < movimento.quantidade:
            raise ProjecaoEstoqueLegadoInvalida("saldo_legado_divergente")

        atualizar_insumo_legado(
            session,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            insumo_id=insumo_id,
            valores={
                "saldo_atual": float(atual - movimento.quantidade),
            },
        )
