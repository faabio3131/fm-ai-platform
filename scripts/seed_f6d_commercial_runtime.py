"""Seed efêmero do gate F6-D em PostgreSQL comercial.

Não habilita FM_AI_TEST_MODE. O banco deve ser descartável (CI/staging de homologação).
"""

from __future__ import annotations

import os

from sqlalchemy import MetaData, Table, create_engine, insert, select
from sqlalchemy.orm import sessionmaker

from core.seguranca.permissoes import Papel
from infra.legacy_product_scope import (
    inserir_ficha_tecnica_legada,
    inserir_insumo_legado,
    inserir_produto_legado,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

TENANT = "tenant-f6d"
UNIDADE = "unidade-f6d"
EMAIL = "caixa-f6d@fm.ai"
PASSWORD = "F6D-Commercial-2026!"
LOJA_ID = 6001


def main() -> None:
    if os.getenv("FM_AI_TEST_MODE") == "1":
        raise RuntimeError("F6-D nao pode executar com FM_AI_TEST_MODE=1")

    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url, future=True)
    run_migrations(engine)

    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with Session.begin() as session:
        metadata = MetaData()
        lojas = Table("lojas", metadata, autoload_with=session.connection())
        mapping = Table(
            "fm_unidade_loja_legacy_v1",
            metadata,
            autoload_with=session.connection(),
        )

        if session.execute(select(lojas.c.id).where(lojas.c.id == LOJA_ID)).scalar_one_or_none() is None:
            session.execute(
                insert(lojas).values(id=LOJA_ID, nome_fantasia="Loja F6-D Staging")
            )

        if (
            session.execute(
                select(mapping.c.tenant_id)
                .where(mapping.c.tenant_id == TENANT)
                .where(mapping.c.unidade_id == UNIDADE)
            ).scalar_one_or_none()
            is None
        ):
            session.execute(
                insert(mapping).values(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    loja_id=LOJA_ID,
                    ativo=True,
                )
            )

        repo = RepositorioIdentidadesSQLAlchemy(session)
        if repo.obter_por_email(EMAIL) is None:
            repo.criar_usuario(
                email=EMAIL,
                password=PASSWORD,
                tenant_id=TENANT,
                unidade_padrao_id=UNIDADE,
                papeis=(Papel.CAIXA,),
                unidades_permitidas=(UNIDADE,),
                usuario_id="caixa-f6d",
            )

        produtos = Table("produtos", MetaData(), autoload_with=session.connection())
        produto_id = session.execute(
            select(produtos.c.id)
            .where(produtos.c.nome == "Produto F6-D")
            .where(produtos.c.loja_id == str(LOJA_ID))
        ).scalar_one_or_none()
        if produto_id is None:
            produto_id = inserir_produto_legado(
                session,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                valores={
                    "nome": "Produto F6-D",
                    "categoria": "Homologacao",
                    "descricao_bruta": "Gate F6-D",
                    "descricao_ai": "Gate F6-D",
                    "preco_venda": 20.0,
                    "custo_total_cmv": 5.0,
                    "margem_exibicao": "75.0%",
                },
            )

        insumos = Table("insumos", MetaData(), autoload_with=session.connection())
        insumo_id = session.execute(
            select(insumos.c.id)
            .where(insumos.c.nome == "Insumo F6-D")
            .where(insumos.c.loja_id == LOJA_ID)
        ).scalar_one_or_none()
        if insumo_id is None:
            insumo_id = inserir_insumo_legado(
                session,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                valores={
                    "nome": "Insumo F6-D",
                    "unidade_medida": "un",
                    "saldo_atual": 100.0,
                    "estoque_minimo": 1.0,
                    "custo_unitario": 5.0,
                },
            )

        fichas = Table("fichas_tecnicas", MetaData(), autoload_with=session.connection())
        ficha_existente = session.execute(
            select(fichas.c.id)
            .where(fichas.c.produto_id == int(produto_id))
            .where(fichas.c.insumo_id == int(insumo_id))
        ).scalar_one_or_none()
        if ficha_existente is None:
            inserir_ficha_tecnica_legada(
                session,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                produto_id=int(produto_id),
                insumo_id=int(insumo_id),
                quantidade=1.0,
            )

    print("F6-D commercial seed ready")


if __name__ == "__main__":
    main()
