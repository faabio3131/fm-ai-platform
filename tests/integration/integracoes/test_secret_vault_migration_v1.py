from __future__ import annotations

from sqlalchemy import create_engine, inspect

from migrations.integration_secret_vault_v1 import upgrade_integration_secret_vault_v1


def test_migration_secret_vault_e_idempotente_e_cria_schema_esperado() -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        upgrade_integration_secret_vault_v1(connection)
        upgrade_integration_secret_vault_v1(connection)

    inspector = inspect(engine)
    tabela = "fm_segredos_integracoes_v1"

    assert tabela in inspector.get_table_names()

    colunas = {coluna["name"] for coluna in inspector.get_columns(tabela)}
    assert colunas == {
        "referencia",
        "tenant_id",
        "unidade_id",
        "provedor",
        "finalidade",
        "ciphertext",
        "criado_por",
        "correlation_id",
        "criado_em",
    }

    pk = inspector.get_pk_constraint(tabela)
    assert pk["constrained_columns"] == ["referencia"]

    indices = {indice["name"] for indice in inspector.get_indexes(tabela)}
    assert "ix_fm_segredos_integracoes_scope_v1" in indices

    scope_index = next(
        indice
        for indice in inspector.get_indexes(tabela)
        if indice["name"] == "ix_fm_segredos_integracoes_scope_v1"
    )
    assert scope_index["column_names"] == [
        "tenant_id",
        "unidade_id",
        "provedor",
        "finalidade",
    ]
