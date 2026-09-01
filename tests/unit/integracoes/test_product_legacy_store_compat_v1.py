import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from infra.legacy_product_scope import (
    ErroEscopoLojaLegada,
    inserir_produto_legado,
    resolver_loja_id_legada,
)
from migrations.unit_legacy_store_mapping_v1 import (
    upgrade_unit_legacy_store_mapping_v1,
)
from scripts.wire_product_legacy_store_compat_v1 import aplicar


def _engine():
    return create_engine("sqlite+pysqlite:///:memory:", future=True)


def _preparar_schema(engine):
    with engine.begin() as conn:
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
                "INSERT INTO lojas (id, nome_fantasia) "
                "VALUES (7, 'Loja antiga')"
            )
        )

        upgrade_unit_legacy_store_mapping_v1(conn)


def _mapear(conn):
    conn.execute(
        text(
            """
            INSERT INTO fm_unidade_loja_legacy_v1
                (tenant_id, unidade_id, loja_id, ativo)
            VALUES
                ('tenant-a', 'unidade-a', 7, TRUE)
            """
        )
    )


def test_resolve_somente_por_mapeamento_explicito():
    engine = _engine()
    _preparar_schema(engine)

    with engine.begin() as conn:
        _mapear(conn)

    with Session(engine) as session:
        loja_id = resolver_loja_id_legada(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
        )

        assert loja_id == 7


def test_unica_loja_existente_nao_autoriza_inferencia():
    engine = _engine()
    _preparar_schema(engine)

    with Session(engine) as session, pytest.raises(
        ErroEscopoLojaLegada,
        match="nenhuma loja legada mapeada",
    ):
        resolver_loja_id_legada(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
        )


def test_outro_tenant_nao_pode_usar_mapeamento():
    engine = _engine()
    _preparar_schema(engine)

    with engine.begin() as conn:
        _mapear(conn)

    with Session(engine) as session, pytest.raises(ErroEscopoLojaLegada):
        resolver_loja_id_legada(
            session,
            tenant_id="tenant-b",
            unidade_id="unidade-a",
        )


def test_mapeamento_inativo_falha_fechado():
    engine = _engine()
    _preparar_schema(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fm_unidade_loja_legacy_v1
                    (tenant_id, unidade_id, loja_id, ativo)
                VALUES
                    ('tenant-a', 'unidade-a', 7, FALSE)
                """
            )
        )

    with Session(engine) as session, pytest.raises(ErroEscopoLojaLegada):
        resolver_loja_id_legada(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
        )


def test_insere_produto_com_tenant_unidade_mapeados():
    engine = _engine()
    _preparar_schema(engine)

    with engine.begin() as conn:
        _mapear(conn)

    with Session(engine) as session:
        novo_id = inserir_produto_legado(
            session,
            tenant_id="tenant-a",
            unidade_id="unidade-a",
            valores={"nome": "X-Burger"},
        )
        session.commit()

        row = session.execute(
            text(
                """
                SELECT loja_id, nome
                FROM produtos
                WHERE id = :id
                """
            ),
            {"id": novo_id},
        ).one()

        assert tuple(row) == (7, "X-Burger")


def test_sem_mapeamento_nao_grava_produto():
    engine = _engine()
    _preparar_schema(engine)

    with Session(engine) as session:
        with pytest.raises(ErroEscopoLojaLegada):
            inserir_produto_legado(
                session,
                tenant_id="tenant-a",
                unidade_id="unidade-a",
                valores={"nome": "Nao deve existir"},
            )

        session.rollback()

        total = session.execute(
            text("SELECT COUNT(*) FROM produtos")
        ).scalar_one()

        assert total == 0


def test_patch_wiring_inclui_tenant_unidade_e_e_idempotente():
    origem = '''class Produto:
    loja_id = Column(String(64), nullable=True, index=True)

                novo_prod = Produto(
                    loja_id=CURRENT_IDENTITY.unidade_id,
                    nome=nome_produto,
                    categoria=categoria,
                    preco_venda=preco_venda_final,
                    custo_total_cmv=cmv_total_calculado,
                )
                db_session.add(novo_prod)
                db_session.commit()

                for item in st.session_state.itens_ficha_tecnica:
                    nova_ft = FichaTecnica(
                        produto_id=novo_prod.id,
                        insumo_id=item["insumo_id"],
                        quantidade_utilizada=item["quantidade"],
                    )
                    db_session.add(nova_ft)
                db_session.commit()

                        novo_prod = Produto(
                            loja_id=CURRENT_IDENTITY.unidade_id,
                            nome=prod.get("nome"),
                            categoria=prod.get("categoria", "Geral"),
                            preco_venda=float(prod.get("preco", 0)),
                            custo_total_cmv=cmv_est,
                            descricao_bruta=prod.get("ingredientes", ""),
                        )
                        db_session.add(novo_prod)
                        qtd_cadastrados += 1
'''

    primeira = aplicar(origem)
    segunda = aplicar(primeira)

    assert primeira == segunda
    assert "loja_id = Column(String" not in primeira
    assert primeira.count("inserir_produto_legado") >= 2

    assert primeira.count(
        "tenant_id=CURRENT_IDENTITY.tenant_id"
    ) == 3

    assert primeira.count(
        "unidade_id=CURRENT_IDENTITY.unidade_id"
    ) == 3
