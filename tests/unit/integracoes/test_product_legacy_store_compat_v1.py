from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from infra.legacy_product_scope import ErroEscopoLojaLegada, inserir_produto_legado
from scripts.wire_product_legacy_store_compat_v1 import aplicar


def test_insere_em_loja_id_inteiro_reutilizando_unica_referencia_historica() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE produtos (id INTEGER PRIMARY KEY, loja_id INTEGER NOT NULL, nome VARCHAR)"))
        conn.execute(text("INSERT INTO produtos (id, loja_id, nome) VALUES (1, 7, 'Existente')"))
    with Session(engine) as session:
        novo_id = inserir_produto_legado(
            session,
            unidade_id="unidade-local",
            valores={"nome": "X-Burger"},
        )
        session.commit()
        row = session.execute(text("SELECT loja_id, nome FROM produtos WHERE id=:id"), {"id": novo_id}).one()
        assert tuple(row) == (7, "X-Burger")


def test_insere_em_loja_id_textual_com_unidade_autenticada() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE produtos (id INTEGER PRIMARY KEY, loja_id VARCHAR(64) NOT NULL, nome VARCHAR)"))
    with Session(engine) as session:
        novo_id = inserir_produto_legado(
            session,
            unidade_id="unidade-local",
            valores={"nome": "X-Burger"},
        )
        session.commit()
        row = session.execute(text("SELECT loja_id, nome FROM produtos WHERE id=:id"), {"id": novo_id}).one()
        assert tuple(row) == ("unidade-local", "X-Burger")


def test_loja_id_inteiro_ambiguo_falha_fechado() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE produtos (id INTEGER PRIMARY KEY, loja_id INTEGER NOT NULL, nome VARCHAR)"))
        conn.execute(text("INSERT INTO produtos VALUES (1, 7, 'A'), (2, 8, 'B')"))
    with Session(engine) as session:
        try:
            inserir_produto_legado(session, unidade_id="unidade-local", valores={"nome": "X"})
        except ErroEscopoLojaLegada as exc:
            assert "múltiplas lojas" in str(exc)
        else:
            raise AssertionError("deveria falhar fechado sem mapeamento determinístico")


def test_patch_remove_tipo_estatico_e_e_idempotente() -> None:
    origem = '''class Produto:\n    loja_id = Column(String(64), nullable=True, index=True)\n\n                novo_prod = Produto(\n                    loja_id=CURRENT_IDENTITY.unidade_id,\n                    nome=nome_produto,\n                    categoria=categoria,\n                    preco_venda=preco_venda_final,\n                    custo_total_cmv=cmv_total_calculado,\n                )\n                db_session.add(novo_prod)\n                db_session.commit()\n\n                for item in st.session_state.itens_ficha_tecnica:\n                    nova_ft = FichaTecnica(\n                        produto_id=novo_prod.id,\n\n                        novo_prod = Produto(\n                            loja_id=CURRENT_IDENTITY.unidade_id,\n                            nome=prod.get("nome"),\n                            categoria=prod.get("categoria", "Geral"),\n                            preco_venda=float(prod.get("preco", 0)),\n                            custo_total_cmv=cmv_est,\n                            descricao_bruta=prod.get("ingredientes", ""),\n                        )\n                        db_session.add(novo_prod)\n                        qtd_cadastrados += 1\n'''
    primeira = aplicar(origem)
    segunda = aplicar(primeira)
    assert primeira == segunda
    assert "loja_id = Column(String" not in primeira
    assert primeira.count("inserir_produto_legado") >= 2
