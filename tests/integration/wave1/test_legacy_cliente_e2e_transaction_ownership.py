from __future__ import annotations

import pytest
from sqlalchemy import Column, Float, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from application import legacy_cliente_e2e_transacoes
from application.legacy_cliente_e2e_transacoes import (
    AplicacaoLegacyClienteE2EV1,
)

Base = declarative_base()


class ClienteTeste(Base):
    __tablename__ = "clientes"

    id = Column(
        Integer,
        primary_key=True,
    )
    nome = Column(
        String,
        nullable=False,
    )
    whatsapp = Column(
        String,
        nullable=False,
        unique=True,
    )
    email = Column(
        String,
        nullable=True,
    )
    documento_fiscal = Column(
        String,
        nullable=True,
    )
    status = Column(
        String,
        nullable=False,
    )
    saldo_cashback = Column(
        Float,
        nullable=False,
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={
            "check_same_thread": False,
        },
        poolclass=StaticPool,
    )

    Base.metadata.create_all(
        engine
    )

    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    application = (
        AplicacaoLegacyClienteE2EV1(
            factory,
            ClienteTeste,
        )
    )

    return (
        engine,
        application,
    )


def test_cadastrar_cliente_e2e_commita_em_uow() -> None:
    engine, application = _infra()

    criado = application.cadastrar(
        nome="Cliente E2E",
        whatsapp="5511999991111",
        email="cliente@example.com",
        documento_fiscal="12345678901",
    )

    assert criado is True

    with Session(engine) as session:
        row = (
            session.query(
                ClienteTeste
            )
            .one()
        )

        assert row.nome == "Cliente E2E"
        assert (
            row.whatsapp
            == "5511999991111"
        )
        assert (
            row.email
            == "cliente@example.com"
        )
        assert (
            row.documento_fiscal
            == "12345678901"
        )
        assert row.status == "Ativo"
        assert row.saldo_cashback == 0.0


def test_cliente_e2e_existente_nao_duplica() -> None:
    engine, application = _infra()

    assert application.cadastrar(
        nome="Primeiro",
        whatsapp="5511999992222",
        email=None,
        documento_fiscal=None,
    )

    criado_novamente = (
        application.cadastrar(
            nome="Segundo",
            whatsapp="5511999992222",
            email=None,
            documento_fiscal=None,
        )
    )

    assert criado_novamente is False

    with Session(engine) as session:
        rows = (
            session.query(
                ClienteTeste
            )
            .all()
        )

        assert len(rows) == 1
        assert rows[0].nome == "Primeiro"


def test_falha_antes_do_commit_faz_rollback_do_cliente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, application = _infra()

    def commit_com_falha(
        uow,
    ) -> None:
        uow.flush()

        raise RuntimeError(
            "falha_commit_cliente_e2e"
        )

    monkeypatch.setattr(
        legacy_cliente_e2e_transacoes.UnitOfWorkV1,
        "commit",
        commit_com_falha,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_commit_cliente_e2e",
    ):
        application.cadastrar(
            nome="Nao Persistir",
            whatsapp="5511999993333",
            email=None,
            documento_fiscal=None,
        )

    with Session(engine) as session:
        total = (
            session.query(
                ClienteTeste
            )
            .count()
        )

        assert total == 0
