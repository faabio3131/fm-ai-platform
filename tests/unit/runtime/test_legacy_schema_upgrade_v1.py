from __future__ import annotations

from sqlalchemy import Float, Integer, String, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


class Base(DeclarativeBase):
    pass


class InsumoAtual(Base):
    __tablename__ = "insumos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str | None] = mapped_column(String)
    unidade_medida: Mapped[str | None] = mapped_column(String)
    saldo_atual: Mapped[float | None] = mapped_column(Float)
    estoque_minimo: Mapped[float | None] = mapped_column(Float)
    custo_unitario: Mapped[float | None] = mapped_column(Float)


def test_upgrade_de_schema_legado_preserva_dados_e_e_idempotente() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE insumos ("
            "id INTEGER PRIMARY KEY, nome VARCHAR UNIQUE, "
            "quantidade_atual FLOAT, unidade VARCHAR, alerta_minimo FLOAT)"
        )
        connection.execute(
            text(
                "INSERT INTO insumos "
                "(id, nome, quantidade_atual, unidade, alerta_minimo) "
                "VALUES (1, 'Farinha', 12.5, 'kg', 3.0)"
            )
        )
        connection.exec_driver_sql(
            "CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome VARCHAR)"
        )
        connection.exec_driver_sql(
            "INSERT INTO clientes (id, nome) VALUES (7, 'Cliente legado')"
        )
        connection.exec_driver_sql(
            "CREATE TABLE produtos (id INTEGER PRIMARY KEY, nome VARCHAR)"
        )
        connection.exec_driver_sql(
            "INSERT INTO produtos (id, nome) VALUES (8, 'Produto legado')"
        )

    # Simula um banco que já registrou 0001--0013: create_all da 0003 não
    # alterou as tabelas acima; apenas a nova migration deve evoluí-las.
    assert run_migrations(engine, migrations=DEFAULT_MIGRATIONS[:13]) == tuple(
        migration.version for migration in DEFAULT_MIGRATIONS[:13]
    )
    assert "saldo_atual" not in {
        column["name"] for column in inspect(engine).get_columns("insumos")
    }

    assert run_migrations(engine) == ("0014_legacy_schema_upgrade_v1",)
    assert run_migrations(engine) == ()

    columns = {
        column["name"] for column in inspect(engine).get_columns("insumos")
    }
    assert {
        "unidade_medida",
        "saldo_atual",
        "estoque_minimo",
        "custo_unitario",
        "data_fabricacao",
        "data_validade",
        "dias_alerta_vencimento",
    } <= columns

    with Session(engine) as session:
        insumo = session.get(InsumoAtual, 1)
        assert insumo is not None
        assert insumo.nome == "Farinha"
        assert insumo.unidade_medida == "kg"
        assert insumo.saldo_atual == 12.5
        assert insumo.estoque_minimo == 3.0
        assert insumo.custo_unitario == 0.0
        assert session.execute(
            text("SELECT nome FROM clientes WHERE id = 7")
        ).scalar_one() == "Cliente legado"
        assert session.execute(
            text("SELECT nome FROM produtos WHERE id = 8")
        ).scalar_one() == "Produto legado"


def test_upgrade_cobre_todas_as_divergencias_aditivas_auditadas() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    expected = {
        "clientes": {"saldo_cashback"},
        "produtos": {"imagem_path"},
        "insumos": {
            "unidade_medida",
            "saldo_atual",
            "estoque_minimo",
            "custo_unitario",
            "data_fabricacao",
            "data_validade",
            "dias_alerta_vencimento",
        },
        "vendas": {"cliente_id", "forma_pagamento", "status_pagamento"},
        "configuracoes_meta": {
            "gateway_provider",
            "gateway_pix_key",
            "gateway_api_key",
        },
    }
    inspector = inspect(engine)
    for table, column_names in expected.items():
        actual = {column["name"] for column in inspector.get_columns(table)}
        assert column_names <= actual
