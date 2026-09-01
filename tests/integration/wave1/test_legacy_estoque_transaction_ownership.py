from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import legacy_estoque_transacoes
from application.legacy_estoque_transacoes import (
    AplicacaoLegacyEstoqueV1,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao

TENANT = "tenant-estoque-sd1e"
UNIDADE = "unidade-estoque-sd1e"


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-estoque",
        papeis=frozenset(
            {
                Papel.ADMINISTRADOR,
            }
        ),
        permissoes=frozenset(
            Permissao
        ),
        correlation_id=(
            "corr-estoque-sd1e"
        ),
        solicitado_em=datetime(
            2026,
            8,
            28,
            12,
            0,
            tzinfo=UTC,
        ),
        origem=(
            "tests.sd1e.legacy_estoque"
        ),
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
                CREATE TABLE
                fm_unidade_loja_legacy_v1 (
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
                CREATE TABLE insumos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    loja_id INTEGER NOT NULL,
                    nome VARCHAR(255) NOT NULL,
                    unidade_medida VARCHAR(32),
                    saldo_atual FLOAT,
                    estoque_minimo FLOAT,
                    custo_unitario FLOAT,
                    data_fabricacao DATETIME,
                    data_validade DATETIME,
                    dias_alerta_vencimento INTEGER
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO
                    fm_unidade_loja_legacy_v1
                    (
                        tenant_id,
                        unidade_id,
                        loja_id,
                        ativo
                    )
                VALUES
                    (
                        :tenant,
                        :unidade,
                        7,
                        TRUE
                    )
                """
            ),
            {
                "tenant":
                    TENANT,
                "unidade":
                    UNIDADE,
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO insumos (
                    id,
                    loja_id,
                    nome,
                    unidade_medida,
                    saldo_atual,
                    estoque_minimo,
                    custo_unitario,
                    dias_alerta_vencimento
                )
                VALUES (
                    1,
                    7,
                    'Arroz',
                    'kg',
                    10.0,
                    2.0,
                    5.0,
                    15
                )
                """
            )
        )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    application = (
        AplicacaoLegacyEstoqueV1(
            factory
        )
    )

    return (
        engine,
        application,
    )


def test_salvar_insumo_commita_na_loja_autenticada() -> None:
    engine, application = _infra()

    insumo_id = application.salvar_insumo(
        _contexto(),
        valores={
            "nome": "Feijao",
            "unidade_medida": "kg",
            "saldo_atual": 8.0,
            "estoque_minimo": 2.0,
            "custo_unitario": 7.5,
            "dias_alerta_vencimento": 15,
        },
    )

    with Session(engine) as session:
        row = session.execute(
            text(
                """
                SELECT
                    id,
                    loja_id,
                    nome,
                    saldo_atual
                FROM insumos
                WHERE id = :id
                """
            ),
            {
                "id": insumo_id,
            },
        ).one()

        assert tuple(row) == (
            insumo_id,
            7,
            "Feijao",
            8.0,
        )


def test_lote_atualiza_existente_e_insere_novo_atomicamente() -> None:
    engine, application = _infra()

    total = application.aplicar_lote_leitura(
        _contexto(),
        itens=(
            {
                "nome": "Arroz",
                "quantidade": 5.0,
                "unidade": "kg",
                "data_validade": None,
            },
            {
                "nome": "Feijao",
                "quantidade": 3.0,
                "unidade": "kg",
                "data_validade": None,
            },
        ),
    )

    assert total == 2

    with Session(engine) as session:
        rows = session.execute(
            text(
                """
                SELECT
                    loja_id,
                    nome,
                    saldo_atual
                FROM insumos
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
                "Arroz",
                15.0,
            ),
            (
                7,
                "Feijao",
                3.0,
            ),
        ]


def test_falha_no_lote_faz_rollback_da_atualizacao_e_insercao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, application = _infra()

    real = (
        legacy_estoque_transacoes
        .inserir_insumo_legado
    )

    def falhar_depois_de_inserir(
        *args,
        **kwargs,
    ):
        real(
            *args,
            **kwargs,
        )

        raise RuntimeError(
            "falha_depois_de_inserir"
        )

    monkeypatch.setattr(
        legacy_estoque_transacoes,
        "inserir_insumo_legado",
        falhar_depois_de_inserir,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_depois_de_inserir",
    ):
        application.aplicar_lote_leitura(
            _contexto(),
            itens=(
                {
                    "nome": "Arroz",
                    "quantidade": 5.0,
                    "unidade": "kg",
                    "data_validade": None,
                },
                {
                    "nome": "Feijao",
                    "quantidade": 3.0,
                    "unidade": "kg",
                    "data_validade": None,
                },
            ),
        )

    with Session(engine) as session:
        rows = session.execute(
            text(
                """
                SELECT
                    nome,
                    saldo_atual
                FROM insumos
                ORDER BY id
                """
            )
        ).all()

        assert [
            tuple(row)
            for row in rows
        ] == [
            (
                "Arroz",
                10.0,
            )
        ]


def test_excluir_insumo_commita_em_uow() -> None:
    engine, application = _infra()

    application.excluir_insumo(
        _contexto(),
        insumo_id=1,
    )

    with Session(engine) as session:
        total = session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM insumos
                WHERE id = 1
                """
            )
        ).scalar_one()

        assert total == 0
