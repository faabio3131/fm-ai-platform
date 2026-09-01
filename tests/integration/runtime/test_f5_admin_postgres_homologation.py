from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session

from core.seguranca.permissoes import Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations

_DATABASE_URL = os.getenv("FM_AI_SD1D_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not _DATABASE_URL,
    reason="FM_AI_SD1D_POSTGRES_URL nao configurada",
)


@contextmanager
def _schema_engine(prefix: str) -> Iterator[Engine]:
    schema = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin = create_engine(_DATABASE_URL, future=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        _DATABASE_URL,
        future=True,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_0036_backfill_admin_aplica_em_postgres_e_registry_fica_idempotente() -> None:
    with _schema_engine("f5_admin") as engine:
        aplicadas_ate_f4 = run_migrations(
            engine,
            DEFAULT_MIGRATIONS[:-1],
        )
        assert "0035_assistente_channel_runtime_v1" in aplicadas_ate_f4
        assert "0036_administracao_proprietario_v1" not in aplicadas_ate_f4

        with Session(engine) as session:
            RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
                email="owner-postgres-f5@example.test",
                password="senha-owner-postgres-fase5",
                admin_pin="472839",
                tenant_id="tenant-postgres-f5",
                unidade_padrao_id="matriz-postgres-f5",
                papeis=(Papel.ADMINISTRADOR,),
                unidades_permitidas=("matriz-postgres-f5",),
                acesso_admin_sensivel=True,
            )
            session.commit()

        assert run_migrations(engine, (DEFAULT_MIGRATIONS[-1],)) == (
            "0036_administracao_proprietario_v1",
        )
        assert run_migrations(engine) == ()

        tables = set(inspect(engine).get_table_names())
        assert {
            "fm_empresas_admin_v1",
            "fm_unidades_admin_v1",
            "fm_configuracoes_estabelecimento_v1",
        } <= tables

        with engine.begin() as connection:
            empresa = connection.execute(
                text(
                    "SELECT tenant_id, nome_exibicao "
                    "FROM fm_empresas_admin_v1 "
                    "WHERE tenant_id = 'tenant-postgres-f5'"
                )
            ).one()
            unidade = connection.execute(
                text(
                    "SELECT tenant_id, unidade_id, versao "
                    "FROM fm_unidades_admin_v1 "
                    "WHERE tenant_id = 'tenant-postgres-f5' "
                    "AND unidade_id = 'matriz-postgres-f5'"
                )
            ).one()
            migration = connection.execute(
                text(
                    "SELECT migration_sha256 FROM fm_schema_migrations "
                    "WHERE version = '0036_administracao_proprietario_v1'"
                )
            ).scalar_one()

        assert empresa.tenant_id == "tenant-postgres-f5"
        assert unidade.unidade_id == "matriz-postgres-f5"
        assert unidade.versao == 1
        assert migration
        assert len(str(migration)) == 64
