"""Compatibilidade segura entre escopo canônico V1 e ``loja_id`` legado.

Código novo nunca infere a loja legada pela quantidade de lojas existentes.
O vínculo deve existir explicitamente em ``fm_unidade_loja_legacy_v1``.

Isso mantém a camada legada atrás de uma fronteira fail-closed e evita vazamento
entre tenants/unidades quando a base crescer.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Integer, MetaData, String, Table, insert, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session


class ErroEscopoLojaLegada(RuntimeError):
    """Não foi possível determinar com segurança a loja legada."""


_MAPPING_TABLE = "fm_unidade_loja_legacy_v1"


def _valor_loja_para_coluna(coluna, loja_id: int) -> int | str:
    """Preserva compatibilidade com ``produtos.loja_id`` textual legado."""

    if isinstance(coluna.type, Integer):
        return int(loja_id)
    if isinstance(coluna.type, String):
        return str(int(loja_id))
    raise ErroEscopoLojaLegada(
        f"tipo de loja_id não suportado em {coluna.table.name}"
    )


def resolver_loja_id_legada(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
) -> int:
    tenant = str(tenant_id).strip()
    unidade = str(unidade_id).strip()

    if not tenant:
        raise ErroEscopoLojaLegada("tenant_id vazio")
    if not unidade:
        raise ErroEscopoLojaLegada("unidade_id vazio")

    bind = session.connection()
    metadata = MetaData()

    try:
        mapping = Table(
            _MAPPING_TABLE,
            metadata,
            autoload_with=bind,
        )
    except Exception as exc:
        raise ErroEscopoLojaLegada(
            "mapeamento canônico unidade/loja ausente; "
            "execute a migration comercial correspondente"
        ) from exc

    stmt = (
        select(mapping.c.loja_id)
        .where(mapping.c.tenant_id == tenant)
        .where(mapping.c.unidade_id == unidade)
        .where(mapping.c.ativo.is_(True))
    )

    resultados = tuple(session.execute(stmt).scalars())

    if not resultados:
        raise ErroEscopoLojaLegada(
            "nenhuma loja legada mapeada para tenant/unidade autenticados"
        )

    if len(resultados) != 1:
        raise ErroEscopoLojaLegada(
            "mapeamento de loja legada ambíguo para tenant/unidade autenticados"
        )

    return int(resultados[0])


def inserir_produto_legado(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    valores: dict[str, Any],
) -> int:
    """Insere produto legado usando somente mapeamento canônico explícito."""

    bind = session.connection()
    table = Table("produtos", MetaData(), autoload_with=bind)

    if "id" not in table.c:
        raise ErroEscopoLojaLegada("tabela produtos sem chave primária id")

    payload = {
        chave: valor
        for chave, valor in valores.items()
        if chave in table.c
    }

    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela="produtos",
    )
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )
    payload["loja_id"] = _valor_loja_para_coluna(
        coluna_loja,
        loja_id,
    )

    resultado = session.execute(
        insert(table)
        .values(**payload)
        .returning(table.c.id)
    )

    return int(resultado.scalar_one())


def _refletir_tabela_scoped(
    session: Session,
    nome_tabela: str,
) -> Table:
    bind = session.connection()

    try:
        table = Table(
            nome_tabela,
            MetaData(),
            autoload_with=bind,
        )
    except Exception as exc:
        raise ErroEscopoLojaLegada(
            f"tabela legada ausente ou inacessível: {nome_tabela}"
        ) from exc

    if "id" not in table.c:
        raise ErroEscopoLojaLegada(
            f"tabela {nome_tabela} sem chave primária id"
        )

    return table


def _exigir_coluna_loja(
    table: Table,
    *,
    nome_tabela: str,
):
    coluna = table.c.get("loja_id")

    if coluna is None:
        raise ErroEscopoLojaLegada(
            f"tabela {nome_tabela} sem loja_id; "
            "não é possível garantir isolamento por unidade"
        )

    return coluna


def _exigir_entidade_da_loja(
    session: Session,
    *,
    table: Table,
    entidade_id: int,
    loja_id: int,
    nome_entidade: str,
):
    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela=table.name,
    )

    stmt = (
        select(table)
        .where(table.c.id == entidade_id)
        .where(
            coluna_loja
            == _valor_loja_para_coluna(coluna_loja, loja_id)
        )
    )

    row = session.execute(stmt).first()

    if row is None:
        raise ErroEscopoLojaLegada(
            f"{nome_entidade} não pertence à loja "
            "da tenant/unidade autenticada"
        )

    return row


def listar_produtos_legados(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
):
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    table = _refletir_tabela_scoped(
        session,
        "produtos",
    )

    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela="produtos",
    )

    stmt = (
        select(table)
        .where(
            coluna_loja
            == _valor_loja_para_coluna(coluna_loja, loja_id)
        )
        .order_by(table.c.id)
    )

    return session.execute(stmt).all()


def listar_insumos_legados(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
):
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    table = _refletir_tabela_scoped(
        session,
        "insumos",
    )

    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela="insumos",
    )

    stmt = (
        select(table)
        .where(
            coluna_loja
            == _valor_loja_para_coluna(coluna_loja, loja_id)
        )
        .order_by(table.c.id)
    )

    return session.execute(stmt).all()


def contar_insumos_legados(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
) -> int:
    return len(
        listar_insumos_legados(
            session,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
        )
    )


def inserir_insumo_legado(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    valores: dict[str, Any],
) -> int:
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    table = _refletir_tabela_scoped(
        session,
        "insumos",
    )

    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela="insumos",
    )

    if "dias_alerta_vencimento" in valores:
        if valores["dias_alerta_vencimento"] is None:
            raise ErroEscopoLojaLegada(
                "dias_alerta_vencimento não pode ser nulo"
            )
    else:
        valores = {**valores, "dias_alerta_vencimento": 15}

    payload = {
        chave: valor
        for chave, valor in valores.items()
        if chave in table.c
    }

    # O chamador nunca escolhe a loja.
    payload["loja_id"] = _valor_loja_para_coluna(
        coluna_loja,
        loja_id,
    )

    resultado = session.execute(
        insert(table)
        .values(**payload)
        .returning(table.c.id)
    )

    return int(resultado.scalar_one())


def inserir_ficha_tecnica_legada(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    produto_id: int,
    insumo_id: int,
    quantidade: Any,
) -> int:
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    produtos = _refletir_tabela_scoped(
        session,
        "produtos",
    )
    insumos = _refletir_tabela_scoped(
        session,
        "insumos",
    )
    fichas = _refletir_tabela_scoped(
        session,
        "fichas_tecnicas",
    )

    _exigir_entidade_da_loja(
        session,
        table=produtos,
        entidade_id=int(produto_id),
        loja_id=loja_id,
        nome_entidade="produto",
    )

    _exigir_entidade_da_loja(
        session,
        table=insumos,
        entidade_id=int(insumo_id),
        loja_id=loja_id,
        nome_entidade="insumo",
    )

    try:
        quantidade_valor = float(quantidade)
    except (TypeError, ValueError) as exc:
        raise ErroEscopoLojaLegada(
            "quantidade da ficha técnica inválida"
        ) from exc

    if quantidade_valor <= 0:
        raise ErroEscopoLojaLegada(
            "quantidade da ficha técnica deve ser positiva"
        )

    payload: dict[str, Any] = {
        "produto_id": int(produto_id),
        "insumo_id": int(insumo_id),
    }

    if "loja_id" in fichas.c:
        payload["loja_id"] = _valor_loja_para_coluna(
            fichas.c.loja_id,
            loja_id,
        )

    if "quantidade_utilizada" not in fichas.c:
        raise ErroEscopoLojaLegada(
            "fichas_tecnicas sem quantidade_utilizada canônica"
        )

    # Autoridade funcional atual.
    payload["quantidade_utilizada"] = quantidade_valor

    # Campo histórico do PostgreSQL real:
    # apenas espelho de compatibilidade, nunca autoridade.
    if "quantidade_usada" in fichas.c:
        payload["quantidade_usada"] = quantidade_valor

    resultado = session.execute(
        insert(fichas)
        .values(**payload)
        .returning(fichas.c.id)
    )

    return int(resultado.scalar_one())


def listar_fichas_produto_legadas(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    produto_id: int,
):
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    produtos = _refletir_tabela_scoped(
        session,
        "produtos",
    )
    fichas = _refletir_tabela_scoped(
        session,
        "fichas_tecnicas",
    )
    insumos = _refletir_tabela_scoped(
        session,
        "insumos",
    )

    # Antes de devolver qualquer ficha, prova que o produto
    # pertence à loja autenticada.
    _exigir_entidade_da_loja(
        session,
        table=produtos,
        entidade_id=int(produto_id),
        loja_id=loja_id,
        nome_entidade="produto",
    )

    stmt = select(fichas).where(
        fichas.c.produto_id == int(produto_id)
    )

    stmt = stmt.order_by(fichas.c.id)
    rows = session.execute(stmt).all()

    for row in rows:
        if "loja_id" in fichas.c:
            valor_ficha = row._mapping.get("loja_id")
            try:
                loja_ficha = int(str(valor_ficha).strip())
            except (TypeError, ValueError) as exc:
                raise ErroEscopoLojaLegada(
                    "ficha técnica sem loja derivada válida"
                ) from exc
            if loja_ficha != loja_id:
                raise ErroEscopoLojaLegada(
                    "ficha técnica não pertence à loja autenticada"
                )

        _exigir_entidade_da_loja(
            session,
            table=insumos,
            entidade_id=int(row.insumo_id),
            loja_id=loja_id,
            nome_entidade="insumo da ficha técnica",
        )

    return rows


def obter_insumo_por_nome_legado(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    nome: str,
):
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    table = _refletir_tabela_scoped(
        session,
        "insumos",
    )

    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela="insumos",
    )

    nome_normalizado = str(nome).strip()

    if not nome_normalizado:
        raise ErroEscopoLojaLegada(
            "nome do insumo vazio"
        )

    stmt = (
        select(table)
        .where(
            coluna_loja
            == _valor_loja_para_coluna(coluna_loja, loja_id)
        )
        .where(table.c.nome == nome_normalizado)
        .order_by(table.c.id)
    )

    rows = session.execute(stmt).all()

    if not rows:
        return None

    if len(rows) != 1:
        raise ErroEscopoLojaLegada(
            "mais de um insumo com o mesmo nome "
            "na unidade autenticada"
        )

    return rows[0]


def obter_insumo_por_id_legado(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    insumo_id: int,
    for_update: bool = False,
):
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )
    table = _refletir_tabela_scoped(session, "insumos")
    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela="insumos",
    )
    stmt = (
        select(table)
        .where(table.c.id == int(insumo_id))
        .where(
            coluna_loja
            == _valor_loja_para_coluna(coluna_loja, loja_id)
        )
    )
    if for_update:
        stmt = stmt.with_for_update()

    rows = session.execute(stmt).all()
    if not rows:
        return None
    if len(rows) != 1:
        raise ErroEscopoLojaLegada(
            "insumo ambíguo no escopo tenant/unidade"
        )
    return rows[0]


def atualizar_insumo_legado(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    insumo_id: int,
    valores: dict[str, Any],
) -> None:
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    table = _refletir_tabela_scoped(
        session,
        "insumos",
    )

    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela="insumos",
    )

    _exigir_entidade_da_loja(
        session,
        table=table,
        entidade_id=int(insumo_id),
        loja_id=loja_id,
        nome_entidade="insumo",
    )

    payload = {
        chave: valor
        for chave, valor in valores.items()
        if chave in table.c
        and chave not in {"id", "loja_id"}
    }

    if not payload:
        return

    resultado = cast(
        CursorResult[Any],
        session.execute(
            table.update()
            .where(table.c.id == int(insumo_id))
            .where(
                coluna_loja
                == _valor_loja_para_coluna(coluna_loja, loja_id)
            )
            .values(**payload)
        ),
    )

    if resultado.rowcount != 1:
        raise ErroEscopoLojaLegada(
            "atualização de insumo não atingiu "
            "exatamente um registro da unidade"
        )


def excluir_insumo_legado(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
    insumo_id: int,
) -> None:
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    table = _refletir_tabela_scoped(
        session,
        "insumos",
    )

    coluna_loja = _exigir_coluna_loja(
        table,
        nome_tabela="insumos",
    )

    _exigir_entidade_da_loja(
        session,
        table=table,
        entidade_id=int(insumo_id),
        loja_id=loja_id,
        nome_entidade="insumo",
    )

    resultado = cast(
        CursorResult[Any],
        session.execute(
            table.delete()
            .where(table.c.id == int(insumo_id))
            .where(
                coluna_loja
                == _valor_loja_para_coluna(coluna_loja, loja_id)
            )
        ),
    )

    if resultado.rowcount != 1:
        raise ErroEscopoLojaLegada(
            "exclusão de insumo não atingiu "
            "exatamente um registro da unidade"
        )


def obter_produto_por_id_legado(
    session,
    *,
    tenant_id: str,
    unidade_id: str,
    produto_id: int,
):
    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )

    produtos = _refletir_tabela_scoped(session, "produtos")
    _exigir_coluna_loja(
        produtos,
        nome_tabela="produtos",
    )

    stmt = (
        produtos.select()
        .where(produtos.c.id == int(produto_id))
        .where(
            produtos.c.loja_id
            == _valor_loja_para_coluna(
                produtos.c.loja_id,
                loja_id,
            )
        )
    )

    rows = session.execute(stmt).all()

    if not rows:
        return None

    if len(rows) != 1:
        raise ErroEscopoLojaLegada(
            "Produto ambíguo no escopo tenant/unidade."
        )

    return rows[0]


def recalcular_cmv_produtos_legados(
    session: Session,
    *,
    tenant_id: str,
    unidade_id: str,
) -> int:
    """Recalcula CMV somente para produtos e insumos da loja autenticada."""

    loja_id = resolver_loja_id_legada(
        session,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
    )
    produtos = _refletir_tabela_scoped(session, "produtos")
    fichas = _refletir_tabela_scoped(session, "fichas_tecnicas")
    insumos = _refletir_tabela_scoped(session, "insumos")
    coluna_produto_loja = _exigir_coluna_loja(
        produtos,
        nome_tabela="produtos",
    )

    produtos_scoped = session.execute(
        select(produtos).where(
            coluna_produto_loja
            == _valor_loja_para_coluna(
                coluna_produto_loja,
                loja_id,
            )
        )
    ).all()

    for produto in produtos_scoped:
        cmv = 0.0
        fichas_produto = session.execute(
            select(fichas).where(
                fichas.c.produto_id == int(produto.id)
            )
        ).all()
        for ficha in fichas_produto:
            insumo = _exigir_entidade_da_loja(
                session,
                table=insumos,
                entidade_id=int(ficha.insumo_id),
                loja_id=loja_id,
                nome_entidade="insumo da ficha técnica",
            )
            cmv += float(ficha.quantidade_utilizada) * float(
                insumo.custo_unitario or 0.0
            )

        valores: dict[str, Any] = {}
        if "custo_total_cmv" in produtos.c:
            valores["custo_total_cmv"] = round(cmv, 2)
        preco = float(produto.preco_venda or 0.0)
        if "margem_exibicao" in produtos.c and preco > 0:
            valores["margem_exibicao"] = f"{((preco - cmv) / preco) * 100:.1f}%"
        if valores:
            session.execute(
                produtos.update()
                .where(produtos.c.id == int(produto.id))
                .where(
                    coluna_produto_loja
                    == _valor_loja_para_coluna(
                        coluna_produto_loja,
                        loja_id,
                    )
                )
                .values(**valores)
            )

    return len(produtos_scoped)
