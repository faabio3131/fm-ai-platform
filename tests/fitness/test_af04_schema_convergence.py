from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlalchemy import Engine, create_engine, event, inspect, text

from migrations.runner import DEFAULT_MIGRATIONS, applied_versions, run_migrations

_BASELINE_VERSION = "0020b_legacy_store_baseline_v1"
_MAPPING_VERSION = "0021_unit_legacy_store_mapping_v1"
_POSTERIOR_VERSIONS = (
    "0022_crm_clientes_persistencia_v1",
    "0023_crm_contact_vault_v1",
    "0024_crm_cliente_legado_mapping_v1",
    "0025_crm_contact_ownership_v1",
    "0026_crm_consentimentos_historico_v1",
    "0027_legacy_catalog_unit_scope_v1",
)
_RELEVANT_TABLES = (
    "lojas",
    "produtos",
    "insumos",
    "fichas_tecnicas",
    "fm_unidade_loja_legacy_v1",
    "crm_clientes_v1",
    "crm_cliente_contatos_v1",
    "crm_contatos_seguros_v1",
    "crm_cliente_legado_v1",
    "crm_consentimentos_v1",
    "fm_schema_migrations",
)


def _engine() -> Engine:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def _versions() -> tuple[str, ...]:
    return tuple(migration.version for migration in DEFAULT_MIGRATIONS)


def _index(version: str) -> int:
    return _versions().index(version)


def _legacy_upgrade_engine() -> Engine:
    engine = _engine()

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE lojas (
                    id INTEGER NOT NULL PRIMARY KEY,
                    nome_fantasia VARCHAR(255) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO lojas (id, nome_fantasia)
                VALUES (7, 'Loja legada preservada')
                """
            )
        )

    historical_sequence = tuple(
        migration
        for migration in DEFAULT_MIGRATIONS
        if migration.version != _BASELINE_VERSION
    )
    run_migrations(engine, migrations=historical_sequence)
    return engine


def _sorted_constraints(
    items: Iterable[Mapping[str, object]],
) -> tuple[tuple, ...]:
    def signature(item: Mapping[str, object]) -> tuple[str, tuple[str, ...]]:
        columns = item.get("column_names")
        if not isinstance(columns, (list, tuple)):
            columns = ()
        return (
            str(item.get("name") or ""),
            tuple(str(column) for column in columns),
        )

    return tuple(
        sorted(signature(item) for item in items)
    )


def _schema_signature(engine: Engine) -> dict[str, dict[str, object]]:
    inspector = inspect(engine)
    available = set(inspector.get_table_names())
    signature: dict[str, dict[str, object]] = {}

    for table in _RELEVANT_TABLES:
        assert table in available
        signature[table] = {
            "columns": tuple(
                (
                    str(column["name"]),
                    str(column["type"]).upper(),
                    bool(column["nullable"]),
                )
                for column in inspector.get_columns(table)
            ),
            "primary_key": tuple(
                str(column)
                for column in inspector.get_pk_constraint(table).get(
                    "constrained_columns"
                )
                or ()
            ),
            "uniques": _sorted_constraints(
                inspector.get_unique_constraints(table)
            ),
            "indexes": tuple(
                sorted(
                    (
                        str(index.get("name") or ""),
                        tuple(
                            str(column)
                            for column in index.get("column_names") or ()
                        ),
                        bool(index.get("unique")),
                    )
                    for index in inspector.get_indexes(table)
                )
            ),
            "foreign_keys": tuple(
                sorted(
                    (
                        tuple(
                            str(column)
                            for column in foreign_key.get("constrained_columns")
                            or ()
                        ),
                        str(foreign_key.get("referred_table") or ""),
                        tuple(
                            str(column)
                            for column in foreign_key.get("referred_columns") or ()
                        ),
                    )
                    for foreign_key in inspector.get_foreign_keys(table)
                )
            ),
        }

    return signature


def test_af04_a_fresh_install_aplica_sequencia_oficial_ate_0027() -> None:
    engine = _engine()

    applied = run_migrations(engine)

    assert applied == _versions()
    with engine.begin() as connection:
        assert applied_versions(connection) == frozenset(_versions())
    assert set(_RELEVANT_TABLES) <= set(inspect(engine).get_table_names())


def test_af04_b_upgrade_legado_preserva_loja_e_chega_ao_schema_final() -> None:
    engine = _legacy_upgrade_engine()

    applied = run_migrations(engine)

    assert applied == (_BASELINE_VERSION,)
    with engine.begin() as connection:
        store = connection.execute(
            text("SELECT id, nome_fantasia FROM lojas WHERE id = 7")
        ).one()
        assert tuple(store) == (7, "Loja legada preservada")
        assert applied_versions(connection) == frozenset(_versions())


def test_af04_c_fresh_e_upgrade_convergem_no_recorte_relevante() -> None:
    fresh = _engine()
    upgrade = _legacy_upgrade_engine()

    run_migrations(fresh)
    run_migrations(upgrade)

    assert _schema_signature(fresh) == _schema_signature(upgrade)


def test_af04_d_reexecucao_e_idempotente_e_preserva_dados() -> None:
    engine = _engine()
    run_migrations(engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO lojas (id, nome_fantasia)
                VALUES (9, 'Loja após bootstrap')
                """
            )
        )

    assert run_migrations(engine) == ()

    with engine.begin() as connection:
        assert connection.execute(
            text("SELECT COUNT(*) FROM lojas WHERE id = 9")
        ).scalar_one() == 1
        assert applied_versions(connection) == frozenset(_versions())


def test_af04_e_dependencias_de_0021_existem_antes_da_execucao() -> None:
    engine = _engine()
    mapping_index = _index(_MAPPING_VERSION)

    run_migrations(engine, migrations=DEFAULT_MIGRATIONS[:mapping_index])

    inspector = inspect(engine)
    assert "lojas" in inspector.get_table_names()
    assert {"id", "nome_fantasia"} <= {
        column["name"] for column in inspector.get_columns("lojas")
    }
    assert inspector.get_pk_constraint("lojas")["constrained_columns"] == ["id"]

    assert run_migrations(
        engine,
        migrations=DEFAULT_MIGRATIONS[: mapping_index + 1],
    ) == (_MAPPING_VERSION,)
    foreign_keys = inspect(engine).get_foreign_keys("fm_unidade_loja_legacy_v1")
    assert any(
        foreign_key["constrained_columns"] == ["loja_id"]
        and foreign_key["referred_table"] == "lojas"
        and foreign_key["referred_columns"] == ["id"]
        for foreign_key in foreign_keys
    )


def test_af04_f_0022_ate_0027_executam_apos_correcao_do_bootstrap() -> None:
    engine = _engine()

    run_migrations(engine)

    with engine.begin() as connection:
        versions = applied_versions(connection)
    assert set(_POSTERIOR_VERSIONS) <= versions
    assert {
        "crm_clientes_v1",
        "crm_cliente_contatos_v1",
        "crm_contatos_seguros_v1",
        "crm_cliente_legado_v1",
        "crm_consentimentos_v1",
    } <= set(inspect(engine).get_table_names())
