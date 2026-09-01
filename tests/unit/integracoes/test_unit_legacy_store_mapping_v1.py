from sqlalchemy import create_engine, inspect, text

from migrations.unit_legacy_store_mapping_v1 import (
    upgrade_unit_legacy_store_mapping_v1,
)


def _engine():
    return create_engine("sqlite+pysqlite:///:memory:", future=True)


def test_cria_mapeamento_unidade_loja_sem_backfill_automatico():
    engine = _engine()

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
                "INSERT INTO lojas (id, nome_fantasia) VALUES (7, 'Loja antiga')"
            )
        )

        upgrade_unit_legacy_store_mapping_v1(conn)

        insp = inspect(conn)

        assert "fm_unidade_loja_legacy_v1" in insp.get_table_names()

        total = conn.execute(
            text("SELECT COUNT(*) FROM fm_unidade_loja_legacy_v1")
        ).scalar_one()

        assert total == 0


def test_mapeamento_preserva_escopo_tenant_unidade_e_loja():
    engine = _engine()

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
                "INSERT INTO lojas (id, nome_fantasia) VALUES (7, 'Loja antiga')"
            )
        )

        upgrade_unit_legacy_store_mapping_v1(conn)

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

        row = conn.execute(
            text(
                """
                SELECT tenant_id, unidade_id, loja_id, ativo
                FROM fm_unidade_loja_legacy_v1
                """
            )
        ).one()

        assert row.tenant_id == "tenant-a"
        assert row.unidade_id == "unidade-a"
        assert row.loja_id == 7
        assert bool(row.ativo) is True


def test_mesma_loja_nao_pode_ser_vinculada_a_duas_unidades():
    engine = _engine()

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
                "INSERT INTO lojas (id, nome_fantasia) VALUES (7, 'Loja antiga')"
            )
        )

        upgrade_unit_legacy_store_mapping_v1(conn)

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

        import pytest
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO fm_unidade_loja_legacy_v1
                        (tenant_id, unidade_id, loja_id, ativo)
                    VALUES
                        ('tenant-b', 'unidade-b', 7, TRUE)
                    """
                )
            )


def test_upgrade_e_idempotente():
    engine = _engine()

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

        upgrade_unit_legacy_store_mapping_v1(conn)
        upgrade_unit_legacy_store_mapping_v1(conn)

        assert "fm_unidade_loja_legacy_v1" in inspect(conn).get_table_names()
