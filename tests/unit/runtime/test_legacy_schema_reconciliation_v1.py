from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from infra.legacy_schema import legacy_metadata
from migrations.legacy_schema_reconciliation_v1 import reconcile_legacy_schema_v1
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


class Base(DeclarativeBase):
    pass


class ProdutoAtual(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str | None] = mapped_column(String)
    categoria: Mapped[str | None] = mapped_column(String)
    descricao_bruta: Mapped[str | None] = mapped_column(Text)
    descricao_ai: Mapped[str | None] = mapped_column(Text)
    preco_venda: Mapped[float | None] = mapped_column(Float)
    custo_total_cmv: Mapped[float | None] = mapped_column(Float)
    margem_exibicao: Mapped[str | None] = mapped_column(String)
    imagem_path: Mapped[str | None] = mapped_column(String)


class InsumoAtual(Base):
    __tablename__ = "insumos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str | None] = mapped_column(String)
    unidade_medida: Mapped[str | None] = mapped_column(String)
    saldo_atual: Mapped[float | None] = mapped_column(Float)
    estoque_minimo: Mapped[float | None] = mapped_column(Float)
    custo_unitario: Mapped[float | None] = mapped_column(Float)
    data_fabricacao: Mapped[datetime | None] = mapped_column(DateTime)
    data_validade: Mapped[datetime | None] = mapped_column(DateTime)
    dias_alerta_vencimento: Mapped[int | None] = mapped_column(Integer)


def _create_minimal_legacy_schema(engine: Engine) -> None:
    statements = (
        "CREATE TABLE usuarios (id INTEGER PRIMARY KEY)",
        "CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome VARCHAR)",
        "CREATE TABLE produtos (id INTEGER PRIMARY KEY, nome VARCHAR)",
        ("CREATE TABLE insumos (id INTEGER PRIMARY KEY, nome VARCHAR, "
        "quantidade_atual FLOAT, unidade VARCHAR, alerta_minimo FLOAT)"),
        "CREATE TABLE fichas_tecnicas (id INTEGER PRIMARY KEY)",
        ("CREATE TABLE vendas (id INTEGER PRIMARY KEY, produto_nome VARCHAR, "
        "cmv_total FLOAT, data_hora DATETIME)"),
        "CREATE TABLE gateway_config (id INTEGER PRIMARY KEY)",
        "CREATE TABLE configuracoes_meta (id INTEGER PRIMARY KEY)",
        "CREATE TABLE contatos_gerenciais (id INTEGER PRIMARY KEY)",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)
        connection.exec_driver_sql(
            "INSERT INTO produtos (id, nome) VALUES (3, 'Produto antigo')"
        )
        connection.exec_driver_sql(
            "INSERT INTO insumos "
            "(id, nome, quantidade_atual, unidade, alerta_minimo) "
            "VALUES (4, 'Insumo antigo', 9.5, 'kg', 2.0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO vendas (id, produto_nome, cmv_total, data_hora) "
            "VALUES (5, 'Produto antigo', 7.25, '2026-01-02 03:04:05')"
        )


def test_0015_reconcilia_todo_schema_legado_e_preserva_dados() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_minimal_legacy_schema(engine)

    run_migrations(engine, migrations=DEFAULT_MIGRATIONS[:14])
    assert "categoria" not in {
        column["name"] for column in inspect(engine).get_columns("produtos")
    }

    assert run_migrations(engine) == ("0015_legacy_schema_reconciliation_v1",)
    assert run_migrations(engine) == ()
    with engine.begin() as connection:
        reconcile_legacy_schema_v1(connection)

    inspector = inspect(engine)
    for table in legacy_metadata.tables.values():
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        assert {column.name for column in table.columns} <= actual

    with Session(engine) as session:
        produto = session.get(ProdutoAtual, 3)
        assert produto is not None
        assert produto.nome == "Produto antigo"
        assert produto.categoria is None
        assert produto.descricao_bruta is None
        assert produto.descricao_ai is None
        assert produto.preco_venda is None
        assert produto.custo_total_cmv is None
        assert produto.margem_exibicao is None
        assert produto.imagem_path is None

        insumo = session.get(InsumoAtual, 4)
        assert insumo is not None
        assert insumo.nome == "Insumo antigo"
        assert insumo.unidade_medida == "kg"
        assert insumo.saldo_atual == 9.5
        assert insumo.estoque_minimo == 2.0
        assert insumo.custo_unitario == 0.0
        assert insumo.dias_alerta_vencimento == 15

        venda = session.execute(
            text(
                "SELECT produto_id, custo_total, data_venda "
                "FROM vendas WHERE id = 5"
            )
        ).one()
        assert venda.produto_id == 3
        assert venda.custo_total == 7.25
        assert str(venda.data_venda).startswith("2026-01-02 03:04:05")
