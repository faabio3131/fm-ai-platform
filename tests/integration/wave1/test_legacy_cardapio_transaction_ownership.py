from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import legacy_cardapio_transacoes
from application.legacy_cardapio_transacoes import (
    AplicacaoLegacyCardapioV1,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao

TENANT = "tenant-cardapio-sd1e"
UNIDADE = "unidade-cardapio-sd1e"


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-cardapio",
        papeis=frozenset(
            {
                Papel.ADMINISTRADOR,
            }
        ),
        permissoes=frozenset(
            Permissao
        ),
        correlation_id="corr-cardapio-sd1e",
        solicitado_em=datetime(
            2026,
            8,
            27,
            23,
            0,
            tzinfo=UTC,
        ),
        origem="tests.sd1e.legacy_cardapio",
        unidades_permitidas=frozenset(
            {
                UNIDADE,
            }
        ),
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE fm_unidade_loja_legacy_v1 (
                    tenant_id VARCHAR(64) NOT NULL,
                    unidade_id VARCHAR(64) NOT NULL,
                    loja_id INTEGER NOT NULL,
                    ativo BOOLEAN NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE produtos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loja_id INTEGER NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    categoria VARCHAR(255),
                    preco_venda FLOAT,
                    custo_total_cmv FLOAT,
                    descricao_bruta TEXT
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE insumos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loja_id INTEGER NOT NULL,
                    nome VARCHAR(255) NOT NULL
                )
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE fichas_tecnicas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    produto_id INTEGER NOT NULL,
                    insumo_id INTEGER NOT NULL,
                    loja_id INTEGER NOT NULL,
                    quantidade_utilizada FLOAT NOT NULL,
                    quantidade_usada FLOAT
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO fm_unidade_loja_legacy_v1
                    (tenant_id, unidade_id, loja_id, ativo)
                VALUES
                    (:tenant, :unidade, 7, TRUE)
                """
            ),
            {
                "tenant": TENANT,
                "unidade": UNIDADE,
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO insumos
                    (id, loja_id, nome)
                VALUES
                    (1, 7, 'Hamburguer'),
                    (2, 7, 'Pao')
                """
            )
        )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    application = AplicacaoLegacyCardapioV1(
        factory
    )

    return (
        engine,
        application,
    )


def test_salvar_prato_e_ficha_commita_atomicamente() -> None:
    engine, application = _infra()

    produto_id = application.salvar_prato_com_ficha(
        _contexto(),
        valores_produto={
            "nome": "Burger SD1E",
            "categoria": "Hamburgueres",
            "preco_venda": 39.90,
            "custo_total_cmv": 12.50,
        },
        itens_ficha=(
            {
                "insumo_id": 1,
                "quantidade": 180.0,
            },
            {
                "insumo_id": 2,
                "quantidade": 1.0,
            },
        ),
    )

    with Session(engine) as session:
        produto = session.execute(
            text(
                """
                SELECT id, loja_id, nome
                FROM produtos
                WHERE id = :produto_id
                """
            ),
            {
                "produto_id": produto_id,
            },
        ).one()

        fichas = session.execute(
            text(
                """
                SELECT produto_id, insumo_id
                FROM fichas_tecnicas
                ORDER BY id
                """
            )
        ).all()

        assert tuple(produto) == (
            produto_id,
            7,
            "Burger SD1E",
        )

        assert [
            tuple(row)
            for row in fichas
        ] == [
            (
                produto_id,
                1,
            ),
            (
                produto_id,
                2,
            ),
        ]


def test_falha_na_ficha_faz_rollback_do_produto_e_da_ficha_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, application = _infra()

    real = (
        legacy_cardapio_transacoes
        .inserir_ficha_tecnica_legada
    )

    chamadas = [0]

    def falhar_depois_da_primeira_ficha(
        *args,
        **kwargs,
    ):
        resultado = real(
            *args,
            **kwargs,
        )

        chamadas[0] += 1

        if chamadas[0] == 1:
            raise RuntimeError(
                "falha_depois_da_ficha_parcial"
            )

        return resultado

    monkeypatch.setattr(
        legacy_cardapio_transacoes,
        "inserir_ficha_tecnica_legada",
        falhar_depois_da_primeira_ficha,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_depois_da_ficha_parcial",
    ):
        application.salvar_prato_com_ficha(
            _contexto(),
            valores_produto={
                "nome": "Nao Persistir",
                "categoria": "Teste",
                "preco_venda": 10.0,
                "custo_total_cmv": 3.0,
            },
            itens_ficha=(
                {
                    "insumo_id": 1,
                    "quantidade": 1.0,
                },
                {
                    "insumo_id": 2,
                    "quantidade": 1.0,
                },
            ),
        )

    with Session(engine) as session:
        assert (
            session.execute(
                text(
                    "SELECT COUNT(*) FROM produtos"
                )
            ).scalar_one()
            == 0
        )

        assert (
            session.execute(
                text(
                    "SELECT COUNT(*) FROM fichas_tecnicas"
                )
            ).scalar_one()
            == 0
        )


def test_importacao_de_cardapio_commita_lote_completo() -> None:
    engine, application = _infra()

    total = application.importar_produtos(
        _contexto(),
        produtos=(
            {
                "nome": "Produto IA 1",
                "categoria": "Geral",
                "preco_venda": 20.0,
                "custo_total_cmv": 6.4,
                "descricao_bruta": "A",
            },
            {
                "nome": "Produto IA 2",
                "categoria": "Geral",
                "preco_venda": 30.0,
                "custo_total_cmv": 9.6,
                "descricao_bruta": "B",
            },
        ),
    )

    assert total == 2

    with Session(engine) as session:
        rows = session.execute(
            text(
                """
                SELECT loja_id, nome
                FROM produtos
                ORDER BY id
                """
            )
        ).all()

        assert [
            tuple(row)
            for row in rows
        ] == [
            (
                7,
                "Produto IA 1",
            ),
            (
                7,
                "Produto IA 2",
            ),
        ]
