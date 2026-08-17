from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.permissoes import Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.modelos_orm import UsuarioSegurancaORM
from migrations.runner import run_migrations


def test_admin_pin_e_individual_separado_da_senha_e_nao_fica_em_texto_puro() -> None:
    engine = create_engine("sqlite:///:memory:")
    applied = run_migrations(engine)
    assert "0017_admin_pin_v1" in applied
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

        # O primeiro administrador existe fisicamente antes de papéis/unidades,
        # cobrindo a regressão de FK observada no PostgreSQL.
        assert identidade.email == "owner@example.test"

        autenticado = ServicoAutenticacao(repo).autenticar(
            email="owner@example.test",
            password="senha-normal-segura-123",
        )
        assert autenticado.usuario_id == identidade.usuario_id

        assert repo.possui_pin_admin(usuario_id=identidade.usuario_id) is True
        assert repo.verificar_pin_admin(usuario_id=identidade.usuario_id, pin="483726") is True
        assert repo.verificar_pin_admin(usuario_id=identidade.usuario_id, pin="483727") is False
        assert (
            repo.verificar_pin_admin(
                usuario_id=identidade.usuario_id,
                pin="123123",
            )
            is False
        )

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
    engine = create_engine("sqlite:///:memory:")
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
