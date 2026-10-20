from __future__ import annotations

from sqlalchemy import create_engine, select

from infra.administracao.modelos_orm import AdminBase, UnidadeAdminORM
from migrations.admin_unit_legacy_store_reconciliation_v1 import (
    upgrade_admin_unit_legacy_store_reconciliation_v1,
)
from migrations.legacy_store_baseline_v1 import (
    lojas_legacy_v1,
    upgrade_legacy_store_baseline_v1,
)
from migrations.unit_legacy_store_mapping_v1 import (
    upgrade_unit_legacy_store_mapping_v1,
)


def test_reconciliation_cria_loja_exclusiva_para_unidade_sem_mapeamento() -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        upgrade_legacy_store_baseline_v1(connection)
        upgrade_unit_legacy_store_mapping_v1(connection)
        AdminBase.metadata.create_all(bind=connection)
        connection.execute(
            UnidadeAdminORM.__table__.insert().values(
                tenant_id="tenant-staging",
                unidade_id="matriz",
                codigo="MATRIZ",
                nome_fantasia="Staging Matriz",
                tipo="matriz",
                documento_fiscal=None,
                telefone=None,
                email=None,
                endereco={},
                horarios={},
                ativa=True,
                versao=1,
            )
        )

        upgrade_admin_unit_legacy_store_reconciliation_v1(connection)

        mapping = connection.exec_driver_sql(
            """
            SELECT tenant_id, unidade_id, loja_id, ativo
            FROM fm_unidade_loja_legacy_v1
            WHERE tenant_id = 'tenant-staging' AND unidade_id = 'matriz'
            """
        ).one()
        assert mapping.tenant_id == "tenant-staging"
        assert mapping.unidade_id == "matriz"
        assert bool(mapping.ativo) is True

        store_name = connection.execute(
            select(lojas_legacy_v1.c.nome_fantasia).where(
                lojas_legacy_v1.c.id == mapping.loja_id
            )
        ).scalar_one()
        assert store_name == "Staging Matriz"


def test_reconciliation_e_idempotente_e_preserva_mapeamento_existente() -> None:
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        upgrade_legacy_store_baseline_v1(connection)
        upgrade_unit_legacy_store_mapping_v1(connection)
        AdminBase.metadata.create_all(bind=connection)

        store_id = connection.execute(
            lojas_legacy_v1.insert()
            .values(nome_fantasia="Loja Existente")
            .returning(lojas_legacy_v1.c.id)
        ).scalar_one()
        connection.exec_driver_sql(
            """
            INSERT INTO fm_unidade_loja_legacy_v1
                (tenant_id, unidade_id, loja_id, ativo)
            VALUES ('tenant-a', 'unidade-a', ?, TRUE)
            """,
            (store_id,),
        )
        connection.execute(
            UnidadeAdminORM.__table__.insert().values(
                tenant_id="tenant-a",
                unidade_id="unidade-a",
                codigo="A",
                nome_fantasia="Nome Administrativo Novo",
                tipo="matriz",
                documento_fiscal=None,
                telefone=None,
                email=None,
                endereco={},
                horarios={},
                ativa=True,
                versao=1,
            )
        )

        upgrade_admin_unit_legacy_store_reconciliation_v1(connection)
        upgrade_admin_unit_legacy_store_reconciliation_v1(connection)

        rows = connection.exec_driver_sql(
            """
            SELECT loja_id
            FROM fm_unidade_loja_legacy_v1
            WHERE tenant_id = 'tenant-a' AND unidade_id = 'unidade-a'
            """
        ).all()
        assert rows == [(store_id,)]
        assert connection.execute(
            select(lojas_legacy_v1.c.id)
        ).scalars().all() == [store_id]
