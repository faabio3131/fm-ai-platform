"""Compatibilidade segura entre unidade textual V1 e ``produtos.loja_id`` legado.

Bases antigas podem possuir ``loja_id`` inteiro, enquanto instalações mais novas usam
identificadores textuais de unidade. A escrita reflete o schema real e nunca inventa
um identificador inteiro quando não há mapeamento determinístico.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer, MetaData, Table, insert, select
from sqlalchemy.orm import Session


class ErroEscopoLojaLegada(RuntimeError):
    """Não foi possível determinar com segurança a loja legada do produto."""


def _resolver_loja_id(session: Session, table: Table, unidade_id: str) -> int | str | None:
    coluna = table.c.get("loja_id")
    if coluna is None:
        return None

    if isinstance(coluna.type, Integer):
        texto = str(unidade_id).strip()
        try:
            return int(texto)
        except ValueError:
            existentes = tuple(
                session.execute(
                    select(coluna)
                    .where(coluna.is_not(None))
                    .distinct()
                    .limit(2)
                ).scalars()
            )
            if len(existentes) == 1:
                return int(existentes[0])
            if not existentes:
                raise ErroEscopoLojaLegada(
                    "produtos.loja_id inteiro não possui referência histórica para esta base"
                )
            raise ErroEscopoLojaLegada(
                "produtos.loja_id inteiro possui múltiplas lojas e não há mapeamento determinístico da unidade autenticada"
            )

    return str(unidade_id)


def inserir_produto_legado(
    session: Session,
    *,
    unidade_id: str,
    valores: dict[str, Any],
) -> int:
    """Insere produto respeitando o tipo real de ``loja_id`` da base conectada."""

    bind = session.get_bind()
    table = Table("produtos", MetaData(), autoload_with=bind)
    payload = {chave: valor for chave, valor in valores.items() if chave in table.c}

    loja_id = _resolver_loja_id(session, table, unidade_id)
    if "loja_id" in table.c:
        payload["loja_id"] = loja_id

    if "id" not in table.c:
        raise ErroEscopoLojaLegada("tabela produtos sem chave primária id")

    resultado = session.execute(insert(table).values(**payload).returning(table.c.id))
    return int(resultado.scalar_one())
