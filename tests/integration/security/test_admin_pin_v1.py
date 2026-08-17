from __future__ import annotations

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.permissoes import Papel, Permissao
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.modelos_orm import (
    UsuarioPapelORM,
    UsuarioSegurancaORM,
    UsuarioUnidadeORM,
)
from migrations.runner import run_migrations


def _sqlite_engine_com_fk() -> Engine:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def test_bootstrap_primeiro_administrador_respeita_fk_com_foreign_keys_ativas() -> None:
    """Regressão do ForeignKeyViolation observado ao criar o primeiro administrador."""

    engine = _sqlite_engine_com_fk()
    run_migrations(engine)

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        identidade = repo.criar_usuario(
            email="first-owner@example.test",
            password="senha-bootstrap-segura-123",
            admin_pin="739284",
            tenant_id="tenant-bootstrap",
            unidade_padrao_id="matriz-1",
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("matriz-1",),
        )
        session.commit()

        usuario = session.get(UsuarioSegurancaORM, identidade.usuario_id)
        papel = session.scalar(
            select(UsuarioPapelORM).where(
                UsuarioPapelORM.usuario_id == identidade.usuario_id
            )
        )
        unidade = session.scalar(
            select(UsuarioUnidadeORM).where(
                UsuarioUnidadeORM.usuario_id == identidade.usuario_id
            )
        )

        assert usuario is not None
        assert papel is not None
        assert papel.papel == Papel.ADMINISTRADOR.value
        assert unidade is not None
        assert unidade.unidade_id == "matriz-1"


def test_admin_pin_e_individual_separado_da_senha_e_nao_fica_em_texto_puro() -> None:
    engine = _sqlite_engine_com_fk()
    applied = run_migrations(engine)
    assert "0017_admin_pin_v1" in applied
    assert "0018_admin_access_authorization_v1" in applied
    assert run_migrations(engine) == ()

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        identidade = repo.criar_usuario(
            email="owner@example.test",
            password="senha-normal-segura-123",
            admin_pin="483726",
            tenant_id="tenant-1",
            unidade_padrao_id="loja-1",
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("loja-1",),
        )
        session.commit()

        assert identidade.email == "owner@example.test"

        autenticado = ServicoAutenticacao(repo).autenticar(
            email="owner@example.test",
            password="senha-normal-segura-123",
        )
        assert autenticado.usuario_id == identidade.usuario_id

        assert repo.possui_pin_admin(usuario_id=identidade.usuario_id) is True
        assert repo.verificar_pin_admin(usuario_id=identidade.usuario_id, pin="483726") is True
        assert repo.verificar_pin_admin(usuario_id=identidade.usuario_id, pin="483727") is False

        row = session.scalar(
            select(UsuarioSegurancaORM).where(
                UsuarioSegurancaORM.usuario_id == identidade.usuario_id
            )
        )
        assert row is not None
        assert row.admin_pin_hash is not None
        assert row.admin_pin_hash != row.senha_hash
        assert "483726" not in row.admin_pin_hash
        assert "senha-normal-segura-123" not in row.senha_hash


def test_usuario_existente_sem_pin_falha_fechado_ate_configurar_pin_individual() -> None:
    engine = _sqlite_engine_com_fk()
    run_migrations(engine)

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        identidade = repo.criar_usuario(
            email="manager@example.test",
            password="outra-senha-normal-456",
            tenant_id="tenant-1",
            unidade_padrao_id="loja-1",
            papeis=(Papel.GERENTE,),
            unidades_permitidas=("loja-1",),
        )
        session.commit()

        assert repo.possui_pin_admin(usuario_id=identidade.usuario_id) is False
        assert repo.verificar_pin_admin(usuario_id=identidade.usuario_id, pin="654321") is False

        repo.definir_pin_admin(usuario_id=identidade.usuario_id, novo_pin="654321")
        session.commit()
        assert repo.possui_pin_admin(usuario_id=identidade.usuario_id) is True
        assert repo.verificar_pin_admin(usuario_id=identidade.usuario_id, pin="654321") is True


def test_gerente_so_recebe_gate_admin_apos_autorizacao_explicita_persistida() -> None:
    engine = _sqlite_engine_com_fk()
    run_migrations(engine)

    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        gerente = repo.criar_usuario(
            email="authorized-manager@example.test",
            password="senha-gerente-segura-789",
            admin_pin="472839",
            tenant_id="tenant-1",
            unidade_padrao_id="loja-1",
            papeis=(Papel.GERENTE,),
            unidades_permitidas=("loja-1",),
        )
        session.commit()

        assert gerente.acesso_admin_sensivel is False
        assert Permissao.ADMIN_ACESSAR not in gerente.permissoes

        repo.definir_acesso_admin_sensivel(
            usuario_id=gerente.usuario_id,
            autorizado=True,
        )
        session.commit()

        recarregado = repo.obter_por_email("authorized-manager@example.test")
        assert recarregado is not None
        assert recarregado.acesso_admin_sensivel is True
        assert Permissao.ADMIN_ACESSAR in recarregado.permissoes

        repo.definir_acesso_admin_sensivel(
            usuario_id=gerente.usuario_id,
            autorizado=False,
        )
        session.commit()
        revogado = repo.obter_por_email("authorized-manager@example.test")
        assert revogado is not None
        assert revogado.acesso_admin_sensivel is False
        assert Permissao.ADMIN_ACESSAR not in revogado.permissoes
