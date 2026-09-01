from sqlalchemy import create_engine, inspect, text

from migrations.client_payment_identity_v1 import upgrade_client_payment_identity_v1
from migrations.runner import DEFAULT_MIGRATIONS


def test_migration_0019_adiciona_dados_de_pagador_sem_perder_cliente_existente() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE clientes ("
                "id INTEGER PRIMARY KEY, "
                "nome VARCHAR NOT NULL, "
                "whatsapp VARCHAR"
                ")"
            )
        )
        connection.execute(
            text(
                "INSERT INTO clientes (id, nome, whatsapp) "
                "VALUES (1, 'Cliente Existente', '5511999999999')"
            )
        )

        upgrade_client_payment_identity_v1(connection)
        upgrade_client_payment_identity_v1(connection)

        columns = {column["name"]: column for column in inspect(connection).get_columns("clientes")}
        assert "email" in columns
        assert "documento_fiscal" in columns
        assert columns["email"]["nullable"] is True
        assert columns["documento_fiscal"]["nullable"] is True

        row = connection.execute(
            text(
                "SELECT id, nome, whatsapp, email, documento_fiscal "
                "FROM clientes WHERE id = 1"
            )
        ).one()
        assert tuple(row) == (
            1,
            "Cliente Existente",
            "5511999999999",
            None,
            None,
        )


def test_runner_preserva_registro_da_0020() -> None:
    versoes = {
        migration.version
        for migration in DEFAULT_MIGRATIONS
    }

    assert "0020_product_unit_scope_compat_v1" in versoes
