"""Catálogo comercial do Delivery sobre o escopo legado governado.

A ficha/estoque legado continua sendo a fonte funcional durante o cutover. Este
adapter apenas projeta uma visão de leitura isolada por tenant/unidade; a reserva
financeira e de estoque permanece no checkout canônico da aplicação.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from core.delivery.erros import ErroDelivery
from core.delivery.modelos import ProdutoDelivery
from infra.legacy_product_scope import (
    listar_fichas_produto_legadas,
    listar_produtos_legados,
    obter_insumo_por_id_legado,
)


def _decimal_nao_negativo(valor: object, *, codigo: str) -> Decimal:
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErroDelivery(codigo) from exc
    if not numero.is_finite() or numero < 0:
        raise ErroDelivery(codigo)
    return numero


def _decimal_positivo(valor: object, *, codigo: str) -> Decimal:
    numero = _decimal_nao_negativo(valor, codigo=codigo)
    if numero <= 0:
        raise ErroDelivery(codigo)
    return numero


class CatalogoDeliverySQLAlchemy:
    """Projeção fail-closed do catálogo da unidade autenticada."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _estoque_disponivel(
        self, *, tenant_id: str, unidade_id: str, produto_id: int
    ) -> Decimal:
        fichas = listar_fichas_produto_legadas(
            self._session,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            produto_id=produto_id,
        )
        if not fichas:
            # Sem ficha não existe prova suficiente de capacidade de produção.
            return Decimal(0)

        capacidades: list[Decimal] = []
        for ficha in fichas:
            quantidade = _decimal_positivo(
                ficha.quantidade_utilizada,
                codigo="quantidade_ficha_delivery_invalida",
            )
            insumo = obter_insumo_por_id_legado(
                self._session,
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                insumo_id=int(ficha.insumo_id),
            )
            if insumo is None:
                raise ErroDelivery("insumo_delivery_indisponivel")
            saldo = _decimal_nao_negativo(
                insumo.saldo_atual,
                codigo="saldo_delivery_invalido",
            )
            capacidades.append(saldo / quantidade)

        return min(capacidades)

    def listar(
        self, *, tenant_id: str, unidade_id: str
    ) -> tuple[ProdutoDelivery, ...]:
        produtos: list[ProdutoDelivery] = []
        for row in listar_produtos_legados(
            self._session,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
        ):
            nome = str(row.nome or "").strip()
            if not nome:
                raise ErroDelivery("produto_delivery_sem_nome")
            preco = _decimal_positivo(
                row.preco_venda,
                codigo="preco_delivery_invalido",
            )
            custo = _decimal_nao_negativo(
                row.custo_total_cmv or 0,
                codigo="custo_delivery_invalido",
            )
            produto_id = int(row.id)
            produtos.append(
                ProdutoDelivery(
                    produto_id=f"legacy:produto:{produto_id}",
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    nome=nome,
                    preco=preco,
                    custo_estimado=custo,
                    estoque_disponivel=self._estoque_disponivel(
                        tenant_id=tenant_id,
                        unidade_id=unidade_id,
                        produto_id=produto_id,
                    ),
                    ativo=True,
                    versao=1,
                )
            )
        return tuple(produtos)
