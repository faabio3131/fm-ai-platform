from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.seguranca.autenticacao import (
    ServicoAutenticacao,
    hash_password,
    verify_password,
)
from core.seguranca.erros import CredenciaisInvalidas, SegredoAusente, UsuarioInativo
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.modelos_orm import SecurityBase


def test_password_hash_is_salted_and_verifiable() -> None:
    first = hash_password("senha-super-segura")
    second = hash_password("senha-super-segura")
    assert first != second
    assert "senha-super-segura" not in first
    assert verify_password("senha-super-segura", first) is True
    assert verify_password("senha-errada-000", first) is False


def test_identity_repository_authenticates_and_builds_rbac_context() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        created = repo.criar_usuario(
            usuario_id="user-1",
            email="ADMIN@EXAMPLE.COM",
            password="senha-super-segura",
            tenant_id="tenant-1",
            unidade_padrao_id="loja-a",
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=("loja-a", "loja-b"),
        )
        session.commit()
        assert created.email == "admin@example.com"

        auth = ServicoAutenticacao(repo)
        identity = auth.autenticar(
            email=" admin@example.com ", password="senha-super-segura"
        )
        context = identity.contexto(origem="web")
        assert context.tenant_id == "tenant-1"
        assert context.unidade_id == "loja-a"
        assert context.unidades_permitidas == frozenset({"loja-a", "loja-b"})
        assert Permissao.USUARIO_GERENCIAR in context.permissoes
        assert Permissao.FINANCEIRO_VISUALIZAR in context.permissoes


def test_authentication_does_not_reveal_unknown_user() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    with Session(engine) as session:
        auth = ServicoAutenticacao(RepositorioIdentidadesSQLAlchemy(session))
        with pytest.raises(CredenciaisInvalidas):
            auth.autenticar(email="nobody@example.com", password="qualquer-senha-123")


def test_inactive_user_is_rejected() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        repo.criar_usuario(
            usuario_id="user-2",
            email="financeiro@example.com",
            password="senha-super-segura",
            tenant_id="tenant-1",
            unidade_padrao_id="loja-a",
            papeis=(Papel.FINANCEIRO,),
        )
        repo.definir_ativo(usuario_id="user-2", ativo=False)
        session.commit()
        with pytest.raises(UsuarioInativo):
            ServicoAutenticacao(repo).autenticar(
                email="financeiro@example.com", password="senha-super-segura"
            )


def test_secret_reference_never_renders_plain_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IFOOD_CLIENT_SECRET", "super-secret-value")
    store = ReferenceSecretStore()
    secret = store.resolve("env:IFOOD_CLIENT_SECRET")
    assert secret.reveal() == "super-secret-value"
    assert str(secret) == "***"
    assert "super-secret-value" not in repr(secret)


def test_missing_secret_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    with pytest.raises(SegredoAusente):
        ReferenceSecretStore().resolve("env:MISSING_SECRET")
