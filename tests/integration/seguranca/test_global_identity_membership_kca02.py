from __future__ import annotations

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from core.seguranca.permissoes import Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.modelos_orm import (
    IdentityMembershipORM,
    IdentityUserORM,
)
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


def test_upgrade_backfill_preserva_usuario_legado_como_identidade_global() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine, migrations=DEFAULT_MIGRATIONS[:-1])

    with Session(engine) as session:
        legado = RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="usuario-legado-kca02",
            email="LEGADO-KCA02@example.com",
            password="Senha-Legado-KCA02-123",
            tenant_id="tenant-legado-kca02",
            unidade_padrao_id="unidade-legado-kca02",
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("unidade-legado-kca02",),
        )
        session.commit()
        assert legado.identity_user_id is None

    assert run_migrations(engine, migrations=(DEFAULT_MIGRATIONS[-1],)) == (
        "0050_global_identity_membership_v1",
    )

    tabelas = set(inspect(engine).get_table_names())
    assert {
        "fm_identity_users_v1",
        "fm_identity_memberships_v1",
        "fm_identity_membership_roles_v1",
        "fm_identity_membership_units_v1",
    } <= tabelas

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        migrada = repo.obter_por_email("legado-kca02@example.com")
        assert migrada is not None
        assert migrada.global_identity_id == "usuario-legado-kca02"
        assert migrada.membership_subject_id == "usuario-legado-kca02"
        assert migrada.tenant_id == "tenant-legado-kca02"
        assert migrada.product_code == "KORDENA"


def test_mesma_identidade_pode_ter_memberships_em_tenants_distintos() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        primeira = repo.criar_usuario(
            email="multi-tenant@example.com",
            password="Senha-Multi-Tenant-123",
            tenant_id="tenant-a",
            unidade_padrao_id="unidade-a",
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("unidade-a",),
        )
        segunda = repo.criar_membership_existente(
            identity_user_id=primeira.global_identity_id,
            tenant_id="tenant-b",
            unidade_padrao_id="unidade-b",
            papeis=(Papel.GERENTE,),
            unidades_permitidas=("unidade-b",),
        )
        session.commit()

        assert primeira.global_identity_id == segunda.global_identity_id
        assert primeira.membership_subject_id != segunda.membership_subject_id
        assert primeira.tenant_id == "tenant-a"
        assert segunda.tenant_id == "tenant-b"

        memberships = repo.listar_memberships(
            identity_user_id=primeira.global_identity_id
        )
        assert {item.tenant_id for item in memberships} == {"tenant-a", "tenant-b"}
        assert len({item.membership_subject_id for item in memberships}) == 2

        global_rows = session.scalars(select(IdentityUserORM)).all()
        membership_rows = session.scalars(select(IdentityMembershipORM)).all()
        assert len(global_rows) == 1
        assert len(membership_rows) == 2


def test_membership_secundaria_tem_rbac_e_unidades_independentes() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        primeira = repo.criar_usuario(
            email="escopos@example.com",
            password="Senha-Escopos-KCA02-123",
            tenant_id="tenant-a",
            unidade_padrao_id="unidade-a1",
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("unidade-a1", "unidade-a2"),
        )
        segunda = repo.criar_membership_existente(
            identity_user_id=primeira.global_identity_id,
            tenant_id="tenant-b",
            unidade_padrao_id="unidade-b1",
            papeis=(Papel.FINANCEIRO,),
            unidades_permitidas=("unidade-b1",),
        )
        session.commit()

        recarregada_a = repo.obter_por_id(usuario_id=primeira.membership_subject_id)
        recarregada_b = repo.obter_por_id(usuario_id=segunda.membership_subject_id)
        assert recarregada_a is not None
        assert recarregada_b is not None
        assert recarregada_a.papeis == frozenset({Papel.ADMINISTRADOR})
        assert recarregada_b.papeis == frozenset({Papel.FINANCEIRO})
        assert recarregada_a.unidades_permitidas == frozenset(
            {"unidade-a1", "unidade-a2"}
        )
        assert recarregada_b.unidades_permitidas == frozenset({"unidade-b1"})


def test_membership_padrao_define_escopo_inicial_do_login() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        primeira = repo.criar_usuario(
            email="default-membership@example.com",
            password="Senha-Default-KCA02-123",
            tenant_id="tenant-a",
            unidade_padrao_id="unidade-a",
            papeis=(Papel.GERENTE,),
            unidades_permitidas=("unidade-a",),
        )
        segunda = repo.criar_membership_existente(
            identity_user_id=primeira.global_identity_id,
            tenant_id="tenant-b",
            unidade_padrao_id="unidade-b",
            papeis=(Papel.GERENTE,),
            unidades_permitidas=("unidade-b",),
            padrao=True,
        )
        session.commit()

        default = repo.obter_por_email("default-membership@example.com")
        assert default is not None
        assert default.membership_subject_id == segunda.membership_subject_id
        assert default.tenant_id == "tenant-b"
