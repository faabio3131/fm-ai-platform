import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from infra.legacy_product_scope import (
    ErroEscopoLojaLegada,
    contar_insumos_legados,
    inserir_ficha_tecnica_legada,
    inserir_insumo_legado,
    listar_fichas_produto_legadas,
    listar_insumos_legados,
    listar_produtos_legados,
)
from migrations.unit_legacy_store_mapping_v1 import (
    upgrade_unit_legacy_store_mapping_v1,
)


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                PRAGMA foreign_keys = ON
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE lojas (
                    id INTEGER PRIMARY KEY,
                    nome_fantasia VARCHAR NOT NULL
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
                    nome VARCHAR NOT NULL,
                    FOREIGN KEY (loja_id) REFERENCES lojas(id)
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
                    nome VARCHAR NOT NULL,
                    unidade_medida VARCHAR NOT NULL,
                    saldo_atual FLOAT,
                    custo_unitario FLOAT,
                    dias_alerta_vencimento INTEGER DEFAULT 15 NOT NULL,
                    FOREIGN KEY (loja_id) REFERENCES lojas(id)
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
                    quantidade_usada FLOAT NOT NULL,
                    FOREIGN KEY (produto_id) REFERENCES produtos(id),
                    FOREIGN KEY (insumo_id) REFERENCES insumos(id),
                    FOREIGN KEY (loja_id) REFERENCES lojas(id)
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO lojas (id, nome_fantasia)
                VALUES
                    (7, 'Loja A'),
                    (8, 'Loja B')
                """
            )
        )

        upgrade_unit_legacy_store_mapping_v1(conn)

        conn.execute(
            text(
                """
                INSERT INTO fm_unidade_loja_legacy_v1
                    (tenant_id, unidade_id, loja_id, ativo)
                VALUES
                    ('tenant-a', 'unidade-a', 7, TRUE),
                    ('tenant-b', 'unidade-b', 8, TRUE)
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO produtos (id, loja_id, nome)
                VALUES
                    (101, 7, 'Produto A'),
                    (201, 8, 'Produto B')
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO insumos
                    (
                        id,
                        loja_id,
                        nome,
                        unidade_medida,
                        saldo_atual,
                        custo_unitario
                    )
                VALUES
                    (11, 7, 'Carne', 'kg', 10, 20),
                    (21, 8, 'Carne', 'kg', 30, 25)
                """
            )
        )

    return engine


def test_lista_produtos_somente_da_unidade_autenticada():
    engine = _engine()

    with Session(engine) as session:
        rows = listar_produtos_legados(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
        )

        assert [row.id for row in rows] == [101]


def test_lista_insumos_somente_da_unidade_autenticada():
    engine = _engine()

    with Session(engine) as session:
        rows = listar_insumos_legados(
            session,
            tenant_id="tenant-b",
            unidade_id="unidade-b",
        )

        assert [row.id for row in rows] == [21]


def test_contagem_de_insumos_e_por_unidade():
    engine = _engine()

    with Session(engine) as session:
        assert (
            contar_insumos_legados(
                session,
                tenant_id="tenant-a",
                unidade_id="unidade-a",
            )
            == 1
        )


def test_insercao_de_insumo_recebe_loja_do_mapeamento():
    engine = _engine()

    with Session(engine) as session:
        novo_id = inserir_insumo_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            valores={
                "nome": "Queijo",
                "unidade_medida": "kg",
                "saldo_atual": 5,
                "custo_unitario": 30,
            },
        )

        session.commit()

        loja_id = session.execute(
            text(
                """
                SELECT loja_id
                FROM insumos
                WHERE id = :id
                """
            ),
            {"id": novo_id},
        ).scalar_one()

        assert loja_id == 7


def test_insercao_de_insumo_materializa_alerta_padrao() -> None:
    engine = _engine()

    with Session(engine) as session:
        novo_id = inserir_insumo_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            valores={"nome": "Tomate", "unidade_medida": "kg"},
        )
        session.commit()
        assert session.execute(
            text(
                "SELECT dias_alerta_vencimento FROM insumos WHERE id = :id"
            ),
            {"id": novo_id},
        ).scalar_one() == 15


def test_insercao_de_insumo_preserva_alerta_explicito() -> None:
    engine = _engine()

    with Session(engine) as session:
        novo_id = inserir_insumo_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            valores={
                "nome": "Queijo alerta",
                "unidade_medida": "kg",
                "dias_alerta_vencimento": 7,
                "loja_id": 8,
            },
        )
        session.commit()
        row = session.execute(
            text(
                "SELECT loja_id, dias_alerta_vencimento FROM insumos WHERE id = :id"
            ),
            {"id": novo_id},
        ).one()
        assert (row.loja_id, row.dias_alerta_vencimento) == (7, 7)


def test_insercao_de_insumo_rejeita_alerta_nulo_explicito() -> None:
    engine = _engine()

    with Session(engine) as session, pytest.raises(
        ErroEscopoLojaLegada,
        match="dias_alerta_vencimento não pode ser nulo",
    ):
        inserir_insumo_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            valores={
                "nome": "Nulo",
                "unidade_medida": "kg",
                "dias_alerta_vencimento": None,
            },
        )


def test_ficha_exige_produto_e_insumo_da_mesma_loja():
    engine = _engine()

    with Session(engine) as session, pytest.raises(ErroEscopoLojaLegada):
        inserir_ficha_tecnica_legada(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            produto_id=101,
            insumo_id=21,
            quantidade=2,
        )


def test_ficha_grava_quantidade_canonica_e_compatibilidade():
    engine = _engine()

    with Session(engine) as session:
        ficha_id = inserir_ficha_tecnica_legada(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            produto_id=101,
            insumo_id=11,
            quantidade=2.5,
        )

        session.commit()

        row = session.execute(
            text(
                """
                SELECT
                    loja_id,
                    quantidade_utilizada,
                    quantidade_usada
                FROM fichas_tecnicas
                WHERE id = :id
                """
            ),
            {"id": ficha_id},
        ).one()

        assert row.loja_id == 7
        assert row.quantidade_utilizada == 2.5
        assert row.quantidade_usada == 2.5


def test_lista_fichas_nao_vaza_entre_lojas():
    engine = _engine()

    with Session(engine) as session:
        inserir_ficha_tecnica_legada(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            produto_id=101,
            insumo_id=11,
            quantidade=1,
        )

        session.commit()

        rows_a = listar_fichas_produto_legadas(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            produto_id=101,
        )

        assert len(rows_a) == 1

        with pytest.raises(ErroEscopoLojaLegada):
            listar_fichas_produto_legadas(
                session,
                tenant_id="tenant-b",
                unidade_id="unidade-b",
                produto_id=101,
            )


def test_busca_insumo_por_nome_respeita_unidade():
    from infra.legacy_product_scope import (
        obter_insumo_por_nome_legado,
    )

    engine = _engine()

    with Session(engine) as session:
        row = obter_insumo_por_nome_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            nome="Carne",
        )

        assert row is not None
        assert row.id == 11
        assert row.loja_id == 7


def test_busca_insumo_nao_enxerga_mesmo_nome_de_outra_loja():
    from infra.legacy_product_scope import (
        obter_insumo_por_nome_legado,
    )

    engine = _engine()

    with Session(engine) as session:
        row_a = obter_insumo_por_nome_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            nome="Carne",
        )

        row_b = obter_insumo_por_nome_legado(
            session,
            tenant_id="tenant-b",
            unidade_id="unidade-b",
            nome="Carne",
        )

        assert row_a.id == 11
        assert row_b.id == 21


def test_atualizacao_de_insumo_nao_pode_cruzar_lojas():
    from infra.legacy_product_scope import (
        atualizar_insumo_legado,
    )

    engine = _engine()

    with Session(engine) as session, pytest.raises(ErroEscopoLojaLegada):
        atualizar_insumo_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            insumo_id=21,
            valores={"saldo_atual": 999},
        )


def test_atualizacao_de_insumo_fica_na_unidade():
    from infra.legacy_product_scope import (
        atualizar_insumo_legado,
    )

    engine = _engine()

    with Session(engine) as session:
        atualizar_insumo_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            insumo_id=11,
            valores={"saldo_atual": 77},
        )

        session.commit()

        saldos = session.execute(
            text(
                """
                SELECT id, saldo_atual
                FROM insumos
                ORDER BY id
                """
            )
        ).all()

        assert saldos[0].id == 11
        assert saldos[0].saldo_atual == 77
        assert saldos[1].id == 21
        assert saldos[1].saldo_atual == 30


def test_exclusao_de_insumo_nao_pode_cruzar_lojas():
    from infra.legacy_product_scope import (
        excluir_insumo_legado,
    )

    engine = _engine()

    with Session(engine) as session, pytest.raises(ErroEscopoLojaLegada):
        excluir_insumo_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            insumo_id=21,
        )


def test_exclusao_remove_somente_insumo_da_unidade():
    from infra.legacy_product_scope import (
        excluir_insumo_legado,
    )

    engine = _engine()

    with Session(engine) as session:
        excluir_insumo_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            insumo_id=11,
        )

        session.commit()

        ids = session.execute(
            text(
                """
                SELECT id
                FROM insumos
                ORDER BY id
                """
            )
        ).scalars().all()

        assert ids == [21]


def test_obter_produto_por_id_respeita_unidade():
    from infra.legacy_product_scope import obter_produto_por_id_legado

    engine = _engine()

    with Session(engine) as session:
        produto = obter_produto_por_id_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            produto_id=101,
        )

        assert produto is not None
        assert produto.id == 101
        assert produto.loja_id == 7
        assert produto.nome == "Produto A"


def test_obter_produto_por_id_nao_cruza_lojas():
    from infra.legacy_product_scope import obter_produto_por_id_legado

    engine = _engine()

    with Session(engine) as session:
        produto = obter_produto_por_id_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            produto_id=201,
        )

        assert produto is None
