from __future__ import annotations

from dataclasses import replace

import pytest
from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infra.legacy_product_scope import (
    ErroEscopoLojaLegada,
    inserir_ficha_tecnica_legada,
    listar_insumos_legados,
)
from migrations.legacy_catalog_unit_scope_v1 import (
    sqlite_hardening_objects,
    upgrade_legacy_catalog_unit_scope_v1,
)
from migrations.manifest import (
    MigrationManifestError,
    assert_migration_manifest,
)
from migrations.runner import DEFAULT_MIGRATIONS, applied_versions, run_migrations

_VERSION = "0027_legacy_catalog_unit_scope_v1"


def _engine() -> Engine:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def _run_to_0026(engine: Engine) -> None:
    target = next(
        index
        for index, migration in enumerate(DEFAULT_MIGRATIONS)
        if migration.version == _VERSION
    )
    run_migrations(engine, migrations=DEFAULT_MIGRATIONS[:target])


def _run_0027(engine: Engine) -> tuple[str, ...]:
    target = next(
        index
        for index, migration in enumerate(DEFAULT_MIGRATIONS)
        if migration.version == _VERSION
    )
    return run_migrations(engine, migrations=DEFAULT_MIGRATIONS[: target + 1])


def _seed_lojas(connection, *lojas: int) -> None:
    for loja_id in lojas:
        connection.execute(
            text(
                "INSERT INTO lojas (id, nome_fantasia) "
                "VALUES (:id, :nome)"
            ),
            {"id": loja_id, "nome": f"Loja {loja_id}"},
        )
        connection.execute(
            text(
                "INSERT INTO fm_unidade_loja_legacy_v1 "
                "(tenant_id, unidade_id, loja_id, ativo) "
                "VALUES (:tenant, :unidade, :loja, TRUE)"
            ),
            {
                "tenant": f"tenant-{loja_id}",
                "unidade": f"unidade-{loja_id}",
                "loja": loja_id,
            },
        )


def _seed_produto(connection, *, produto_id: int, loja_id: int, nome: str) -> None:
    connection.execute(
        text(
            "INSERT INTO produtos "
            "(id, loja_id, nome, preco_venda, custo_total_cmv) "
            "VALUES (:id, :loja, :nome, 20, 5)"
        ),
        {"id": produto_id, "loja": loja_id, "nome": nome},
    )


def _seed_insumo(connection, *, insumo_id: int, nome: str, saldo: float = 10) -> None:
    connection.execute(
        text(
            "INSERT INTO insumos "
            "(id, nome, unidade_medida, saldo_atual, estoque_minimo, custo_unitario) "
            "VALUES (:id, :nome, 'kg', :saldo, 1, 2)"
        ),
        {"id": insumo_id, "nome": nome, "saldo": saldo},
    )


def _seed_ficha(
    connection,
    *,
    ficha_id: int,
    produto_id: int,
    insumo_id: int,
) -> None:
    connection.execute(
        text(
            "INSERT INTO fichas_tecnicas "
            "(id, produto_id, insumo_id, quantidade_utilizada) "
            "VALUES (:id, :produto, :insumo, 1)"
        ),
        {"id": ficha_id, "produto": produto_id, "insumo": insumo_id},
    )


def _two_store_catalog() -> Engine:
    engine = _engine()
    _run_to_0026(engine)
    with engine.begin() as connection:
        _seed_lojas(connection, 7, 8)
        _seed_produto(connection, produto_id=101, loja_id=7, nome="Produto A")
        _seed_produto(connection, produto_id=201, loja_id=8, nome="Produto B")
        _seed_insumo(connection, insumo_id=11, nome="Insumo A", saldo=10)
        _seed_insumo(connection, insumo_id=21, nome="Insumo B", saldo=20)
        _seed_ficha(connection, ficha_id=1, produto_id=101, insumo_id=11)
        _seed_ficha(connection, ficha_id=2, produto_id=201, insumo_id=21)
    assert _run_0027(engine) == (_VERSION,)
    return engine


def _schema_signature(engine: Engine) -> dict[str, object]:
    inspector = inspect(engine)
    return {
        "insumos_columns": tuple(
            (column["name"], str(column["type"]).upper())
            for column in inspector.get_columns("insumos")
        ),
        "insumos_fks": tuple(
            sorted(
                (
                    tuple(fk.get("constrained_columns") or ()),
                    fk.get("referred_table"),
                    tuple(fk.get("referred_columns") or ()),
                )
                for fk in inspector.get_foreign_keys("insumos")
            )
        ),
        "insumos_indexes": tuple(
            sorted(
                (
                    index.get("name"),
                    tuple(index.get("column_names") or ()),
                    bool(index.get("unique")),
                )
                for index in inspector.get_indexes("insumos")
            )
        ),
        "fichas_columns": tuple(
            column["name"]
            for column in inspector.get_columns("fichas_tecnicas")
        ),
    }


def test_af31_a_fresh_install_contem_schema_de_escopo_necessario() -> None:
    engine = _engine()
    assert _VERSION in run_migrations(engine)

    inspector = inspect(engine)
    assert "loja_id" in {
        column["name"] for column in inspector.get_columns("insumos")
    }
    assert "loja_id" not in {
        column["name"]
        for column in inspector.get_columns("fichas_tecnicas")
    }
    assert any(
        fk["constrained_columns"] == ["loja_id"]
        and fk["referred_table"] == "lojas"
        and fk["referred_columns"] == ["id"]
        for fk in inspector.get_foreign_keys("insumos")
    )
    assert "ix_insumos_loja_id_v1" in {
        index["name"] for index in inspector.get_indexes("insumos")
    }
    with engine.begin() as connection:
        triggers = set(
            connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'trigger' AND tbl_name = 'insumos'"
                )
            ).scalars()
        )
        assert set(sqlite_hardening_objects()) <= triggers
        _seed_lojas(connection, 7)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO insumos (nome, unidade_medida) "
                    "VALUES ('Sem loja', 'kg')"
                )
            )


def test_af31_b_upgrade_single_store_faz_backfill_e_preserva_dados() -> None:
    engine = _engine()
    _run_to_0026(engine)
    with engine.begin() as connection:
        _seed_lojas(connection, 7)
        _seed_insumo(connection, insumo_id=11, nome="Tomate", saldo=12.5)

    assert _run_0027(engine) == (_VERSION,)
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT nome, saldo_atual, loja_id FROM insumos WHERE id = 11"
            )
        ).one()
        assert tuple(row) == ("Tomate", 12.5, 7)


def test_af31_c_inferencia_por_ficha_de_uma_loja_e_deterministica() -> None:
    engine = _engine()
    _run_to_0026(engine)
    with engine.begin() as connection:
        _seed_lojas(connection, 7, 8)
        _seed_produto(connection, produto_id=101, loja_id=8, nome="Produto B")
        _seed_insumo(connection, insumo_id=11, nome="Queijo")
        _seed_ficha(connection, ficha_id=1, produto_id=101, insumo_id=11)

    assert _run_0027(engine) == (_VERSION,)
    with engine.begin() as connection:
        assert connection.execute(
            text("SELECT loja_id FROM insumos WHERE id = 11")
        ).scalar_one() == 8


def test_af31_d_insumo_de_produtos_de_lojas_diferentes_falha_fechado() -> None:
    engine = _engine()
    _run_to_0026(engine)
    with engine.begin() as connection:
        _seed_lojas(connection, 7, 8)
        _seed_produto(connection, produto_id=101, loja_id=7, nome="Produto A")
        _seed_produto(connection, produto_id=201, loja_id=8, nome="Produto B")
        _seed_insumo(connection, insumo_id=11, nome="Ambíguo")
        _seed_ficha(connection, ficha_id=1, produto_id=101, insumo_id=11)
        _seed_ficha(connection, ficha_id=2, produto_id=201, insumo_id=11)

    with pytest.raises(RuntimeError, match="lojas diferentes"):
        _run_0027(engine)
    with engine.begin() as connection:
        assert _VERSION not in applied_versions(connection)


def test_af31_e_insumo_sem_pista_multi_loja_falha_fechado() -> None:
    engine = _engine()
    _run_to_0026(engine)
    with engine.begin() as connection:
        _seed_lojas(connection, 7, 8)
        _seed_insumo(connection, insumo_id=11, nome="Sem pista")

    with pytest.raises(RuntimeError, match="sem loja determinística"):
        _run_0027(engine)
    with engine.begin() as connection:
        assert _VERSION not in applied_versions(connection)


def test_af31_f_produto_e_insumo_cross_store_nao_formam_ficha() -> None:
    engine = _two_store_catalog()
    with Session(engine) as session, pytest.raises(ErroEscopoLojaLegada):
        inserir_ficha_tecnica_legada(
            session,
            tenant_id="tenant-7",
            unidade_id="unidade-7",
            produto_id=101,
            insumo_id=21,
            quantidade=1,
        )


def test_af31_g_leitura_de_uma_loja_nao_retorna_insumo_da_outra() -> None:
    engine = _two_store_catalog()
    with Session(engine) as session:
        rows_a = listar_insumos_legados(
            session,
            tenant_id="tenant-7",
            unidade_id="unidade-7",
        )
        rows_b = listar_insumos_legados(
            session,
            tenant_id="tenant-8",
            unidade_id="unidade-8",
        )
        assert [row.id for row in rows_a] == [11]
        assert [row.id for row in rows_b] == [21]


def test_af31_h_reexecucao_nao_duplica_nem_corrompe() -> None:
    engine = _engine()
    _run_to_0026(engine)
    with engine.begin() as connection:
        _seed_lojas(connection, 7)
        _seed_insumo(connection, insumo_id=11, nome="Preservado", saldo=33)
        upgrade_legacy_catalog_unit_scope_v1(connection)
        upgrade_legacy_catalog_unit_scope_v1(connection)
        row = connection.execute(
            text(
                "SELECT nome, saldo_atual, loja_id FROM insumos WHERE id = 11"
            )
        ).one()
        assert tuple(row) == ("Preservado", 33.0, 7)
        assert connection.execute(
            text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type = 'index' AND name = 'ix_insumos_loja_id_v1'"
            )
        ).scalar_one() == 1


def test_af31_i_fresh_e_upgrade_convergem_no_recorte_relevante() -> None:
    fresh = _engine()
    upgrade = _engine()
    run_migrations(fresh)
    _run_to_0026(upgrade)
    with upgrade.begin() as connection:
        _seed_lojas(connection, 7)
        _seed_insumo(connection, insumo_id=11, nome="Legado")
    run_migrations(upgrade)
    assert _schema_signature(fresh) == _schema_signature(upgrade)


def test_af31_j_manifest_cobre_0027_e_rejeita_mutacao() -> None:
    target = next(
        index
        for index, migration in enumerate(DEFAULT_MIGRATIONS)
        if migration.version == _VERSION
    )
    assert_migration_manifest(DEFAULT_MIGRATIONS)

    def migration_mutada(connection) -> None:
        upgrade_legacy_catalog_unit_scope_v1(connection)

    mutadas = list(DEFAULT_MIGRATIONS)
    mutadas[target] = replace(mutadas[target], apply=migration_mutada)
    with pytest.raises(
        MigrationManifestError,
        match="migration historica alterada",
    ):
        assert_migration_manifest(mutadas)
