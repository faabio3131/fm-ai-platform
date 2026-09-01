from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application import gerente_ia_transacoes as transacoes
from core.seguranca.permissoes import Papel
from infra.gerente_ia.modelos_orm import IdentidadeAssistenteORM
from infra.seguranca.adaptador_sqlalchemy import (
    RepositorioIdentidadesSQLAlchemy,
)
from migrations.runner import run_migrations

SENHA = "Senha-Segura-123"


def _infra():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    return engine, factory


def _seed_usuario(factory) -> None:
    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(
            session
        ).criar_usuario(
            email="admin@example.com",
            password=SENHA,
            tenant_id="tenant-a",
            unidade_padrao_id="loja-1",
            papeis=(Papel.ADMINISTRADOR,),
        )
        session.commit()


def test_application_commit_persiste_identidade_assistente() -> None:
    engine, factory = _infra()
    _seed_usuario(factory)

    identidade = transacoes.configurar_identidade_assistente_v1(
        session_factory=factory,
        secret_store=None,
        email="admin@example.com",
        password=SENHA,
        origem="core_http_v1",
        correlation_id="corr-commit",
        nome_publico="Lia",
        atributos={"tom": "acolhedor"},
        versao_esperada=None,
    )

    assert identidade.nome_publico == "Lia"

    with Session(engine) as session:
        persistida = session.scalar(
            select(IdentidadeAssistenteORM).where(
                IdentidadeAssistenteORM.tenant_id
                == "tenant-a",
                IdentidadeAssistenteORM.unidade_id
                == "loja-1",
            )
        )

        assert persistida is not None
        assert persistida.nome_publico == "Lia"


def test_application_rollback_remove_flush_parcial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, factory = _infra()
    _seed_usuario(factory)

    class IdentidadeComFalha:
        def __init__(self, session: Session) -> None:
            self.session = session

        def configurar(
            self,
            *,
            contexto,
            nome_publico,
            atributos,
            versao_esperada,
        ):
            del versao_esperada

            self.session.add(
                IdentidadeAssistenteORM(
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    nome_publico=nome_publico,
                    atributos=atributos,
                    versao=1,
                    atualizado_por=contexto.usuario_id,
                    correlation_id=contexto.correlation_id,
                    criado_em=datetime.now(timezone.utc),
                    atualizado_em=datetime.now(timezone.utc),
                )
            )

            self.session.flush()

            raise RuntimeError(
                "falha_depois_do_flush"
            )

    class RuntimeComFalha:
        def __init__(self, session: Session) -> None:
            self.identidade_assistente = (
                IdentidadeComFalha(session)
            )

    def fake_compor_runtime(
        *,
        session,
        secret_store=None,
        planejador_llm=None,
    ):
        del secret_store, planejador_llm
        return RuntimeComFalha(session)

    monkeypatch.setattr(
        transacoes,
        "compor_runtime_gerente_ia",
        fake_compor_runtime,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_depois_do_flush",
    ):
        transacoes.configurar_identidade_assistente_v1(
            session_factory=factory,
            secret_store=None,
            email="admin@example.com",
            password=SENHA,
            origem="core_http_v1",
            correlation_id="corr-rollback",
            nome_publico="Nao Persistir",
            atributos={"tom": "teste"},
            versao_esperada=None,
        )

    with Session(engine) as session:
        persistida = session.scalar(
            select(IdentidadeAssistenteORM).where(
                IdentidadeAssistenteORM.tenant_id
                == "tenant-a",
                IdentidadeAssistenteORM.unidade_id
                == "loja-1",
            )
        )

        assert persistida is None
