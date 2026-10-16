"""Garantias do cache estrutural legado: menos SQL sem vazar dados ou escopos."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import infra.legacy_product_scope as legacy
from migrations.runner import Migration, run_migrations


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE fm_unidade_loja_legacy_v1 "
            "(tenant_id VARCHAR, unidade_id VARCHAR, loja_id INTEGER, ativo BOOLEAN)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE produtos (id INTEGER PRIMARY KEY, loja_id VARCHAR, "
            "nome VARCHAR, preco_venda FLOAT, ativo BOOLEAN)"
        )
        conn.execute(
            text(
                "INSERT INTO fm_unidade_loja_legacy_v1 VALUES "
                "('tenant-a','unit-a',11,1),('tenant-b','unit-b',22,1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO produtos VALUES "
                "(1,'11','X-Bacon',30.0,1),(2,'22','Pizza',55.0,1)"
            )
        )
    return engine


def _query_count(engine, operation):
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        result = operation()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    return result, statements


def test_catalog_reflection_cached_without_caching_product_or_scope():
    engine = _engine()
    factory = sessionmaker(bind=engine)

    def products(tenant, unit):
        with factory() as session:
            return legacy.listar_produtos_legados(
                session, tenant_id=tenant, unidade_id=unit
            )

    try:
        cold, initial_sql = _query_count(
            engine, lambda: products("tenant-a", "unit-a")
        )
        warm, cached_sql = _query_count(
            engine, lambda: products("tenant-a", "unit-a")
        )
        assert len(cold) == len(warm) == 1
        assert str(warm[0]._mapping["nome"]) == "X-Bacon"
        # Os dois SELECTs canônicos continuam: mapping da unidade + produtos.
        assert len(cached_sql) == 2
        assert len(initial_sql) >= len(cached_sql) + 5
        assert all("PRAGMA" not in sql.upper() for sql in cached_sql)

        # Mesmo Engine compartilhado entre empresas: o cache não pode
        # memorizar loja, tenant, resultado nem preço.
        other = products("tenant-b", "unit-b")
        assert len(other) == 1
        assert str(other[0]._mapping["nome"]) == "Pizza"

        with engine.begin() as conn:
            conn.execute(
                text("UPDATE produtos SET preco_venda=42 WHERE id=1")
            )
        again = products("tenant-a", "unit-a")
        assert float(again[0]._mapping["preco_venda"]) == 42.0
        assert len(products("tenant-b", "unit-b")) == 1

        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE fm_unidade_loja_legacy_v1 "
                    "SET ativo=0 WHERE tenant_id='tenant-a'"
                )
            )
        with pytest.raises(legacy.ErroEscopoLojaLegada):
            products("tenant-a", "unit-a")
    finally:
        legacy.invalidar_cache_reflexao_legada(engine)
        engine.dispose()


def _change_schema(connection):
    connection.exec_driver_sql(
        "ALTER TABLE produtos ADD COLUMN marcador_pos_migration VARCHAR"
    )


def test_applied_migration_invalidates_cached_legacy_metadata():
    engine = _engine()
    try:
        with Session(engine) as session:
            table = legacy._refletir_tabela_scoped(session, "produtos")
            assert "marcador_pos_migration" not in table.c

        versions = run_migrations(
            engine, migrations=(Migration("test_legacy_cache_refresh", _change_schema),)
        )
        assert versions == ("test_legacy_cache_refresh",)
        with Session(engine) as session:
            refreshed = legacy._refletir_tabela_scoped(session, "produtos")
            assert "marcador_pos_migration" in refreshed.c
            assert refreshed is not table
    finally:
        legacy.invalidar_cache_reflexao_legada(engine)
        engine.dispose()


def test_connection_failure_during_reflection_propagates_as_database_error(monkeypatch):
    engine = _engine()

    def disconnected(*args, **kwargs):
        raise OperationalError(
            "PRAGMA table_info", {}, RuntimeError("database disconnected")
        )

    try:
        monkeypatch.setattr(legacy, "Table", disconnected)
        with Session(engine) as session:
            with pytest.raises(OperationalError):
                legacy.resolver_loja_id_legada(
                    session, tenant_id="tenant-a", unidade_id="unit-a"
                )
    finally:
        legacy.invalidar_cache_reflexao_legada(engine)
        engine.dispose()


def test_reflection_missing_table_is_domain_error_but_not_cached():
    engine = _engine()
    try:
        with Session(engine) as session:
            with pytest.raises(legacy.ErroEscopoLojaLegada, match="tabela legada"):
                legacy._refletir_tabela_scoped(session, "tabela_que_nao_existe")
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE tabela_que_nao_existe (id INTEGER PRIMARY KEY, "
                "loja_id INTEGER)"
            )
        with Session(engine) as session:
            assert legacy._refletir_tabela_scoped(
                session, "tabela_que_nao_existe"
            ).name == "tabela_que_nao_existe"
    finally:
        legacy.invalidar_cache_reflexao_legada(engine)
        engine.dispose()


def test_reflection_isolated_by_engine_and_concurrent_sessions(tmp_path):
    # Um Engine por banco: metadata nunca é compartilhada por processo.
    engines = []
    try:
        for index in range(2):
            engine = create_engine(
                f"sqlite:///{tmp_path / ('isolation-' + str(index) + '.db')}",
                pool_size=6,
                max_overflow=0,
            )
            engines.append(engine)
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "CREATE TABLE produtos (id INTEGER PRIMARY KEY, loja_id VARCHAR)"
                )

        def table(engine):
            with Session(engine) as session:
                return legacy._refletir_tabela_scoped(session, "produtos")

        with ThreadPoolExecutor(max_workers=10) as executor:
            tables = list(executor.map(
                lambda i: table(engines[i % 2]), range(30)
            ))
        assert all(item is tables[0] for item in tables[::2])
        assert all(item is tables[1] for item in tables[1::2])
        assert tables[0] is not tables[1]
    finally:
        for engine in engines:
            legacy.invalidar_cache_reflexao_legada(engine)
            engine.dispose()
