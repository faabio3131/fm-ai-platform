from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from migrations.product_unit_scope_compat_v1 import (
    upgrade_product_unit_scope_compat_v1,
)
from scripts.wire_product_legacy_store_compat_v1 import aplicar as aplicar_compat
from scripts.wire_product_unit_scope_v1 import aplicar as aplicar_unit_scope


APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def _estado_canonico(source: str) -> str:
    """Normaliza tanto o app pré-compat quanto o já convertido para o wiring atual."""

    return aplicar_compat(aplicar_unit_scope(source))


def test_patch_mapeia_loja_e_preenche_unidade_nos_dois_fluxos() -> None:
    atualizado = _estado_canonico(APP_SOURCE)

    assert 'loja_id = Column(String(64), nullable=True, index=True)' not in atualizado
    assert "loja_id=CURRENT_IDENTITY.unidade_id" not in atualizado
    assert atualizado.count("inserir_produto_legado(") == 2
    assert atualizado.count("unidade_id=CURRENT_IDENTITY.unidade_id") == 2
    assert "produto_id=novo_prod_id" in atualizado


def test_patch_e_idempotente() -> None:
    primeira = _estado_canonico(APP_SOURCE)
    segunda = _estado_canonico(primeira)
    assert segunda == primeira


def test_migration_adiciona_coluna_e_indice_sem_inventar_unidade_historica() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE produtos ("
                "id INTEGER PRIMARY KEY, nome VARCHAR NOT NULL"
                ")"
            )
        )
        connection.execute(text("INSERT INTO produtos (id, nome) VALUES (1, 'Legado')"))
        upgrade_product_unit_scope_compat_v1(connection)
        upgrade_product_unit_scope_compat_v1(connection)

        colunas = {item["name"] for item in inspect(connection).get_columns("produtos")}
        indices = {item["name"] for item in inspect(connection).get_indexes("produtos")}
        assert "loja_id" in colunas
        assert "ix_produtos_loja_id_v1" in indices
        assert connection.execute(text("SELECT loja_id FROM produtos WHERE id = 1")).scalar() is None


def test_migration_preserva_loja_id_existente_not_null() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE produtos ("
                "id INTEGER PRIMARY KEY, loja_id VARCHAR(64) NOT NULL, nome VARCHAR NOT NULL"
                ")"
            )
        )
        connection.execute(
            text("INSERT INTO produtos (id, loja_id, nome) VALUES (1, 'unidade-a', 'Existente')")
        )
        upgrade_product_unit_scope_compat_v1(connection)

        linha = connection.execute(
            text("SELECT loja_id, nome FROM produtos WHERE id = 1")
        ).one()
        assert linha == ("unidade-a", "Existente")
