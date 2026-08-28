from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from application import legacy_gateway_teste_transacoes
from application.legacy_gateway_teste_transacoes import (
    AplicacaoLegacyGatewayTesteV1,
)

Base = declarative_base()


class ConfiguracaoMetaTeste(Base):
    __tablename__ = "configuracoes_meta"

    id = Column(
        Integer,
        primary_key=True,
    )
    gateway_provider = Column(
        String,
        nullable=True,
    )
    gateway_pix_key = Column(
        String,
        nullable=True,
    )
    gateway_api_key = Column(
        String,
        nullable=True,
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
        AplicacaoLegacyGatewayTesteV1(
            factory,
            ConfiguracaoMetaTeste,
        )
    )

    return (
        engine,
        application,
    )


def test_salvar_gateway_e2e_commita_em_uow() -> None:
    engine, application = _infra()

    application.salvar(
        provider="Mercado Pago",
        pix_key="pix-sandbox",
        api_key="token-sandbox",
    )

    with Session(engine) as session:
        rows = (
            session.query(
                ConfiguracaoMetaTeste
            )
            .all()
        )

        assert len(rows) == 1

        assert (
            rows[0].gateway_provider
            == "Mercado Pago"
        )
        assert (
            rows[0].gateway_pix_key
            == "pix-sandbox"
        )
        assert (
            rows[0].gateway_api_key
            == "token-sandbox"
        )


def test_salvar_gateway_e2e_atualiza_registro_existente() -> None:
    engine, application = _infra()

    application.salvar(
        provider="Mercado Pago",
        pix_key="pix-1",
        api_key="token-1",
    )

    application.salvar(
        provider="Asaas",
        pix_key="pix-2",
        api_key="token-2",
    )

    with Session(engine) as session:
        rows = (
            session.query(
                ConfiguracaoMetaTeste
            )
            .all()
        )

        assert len(rows) == 1

        assert (
            rows[0].gateway_provider
            == "Asaas"
        )
        assert (
            rows[0].gateway_pix_key
            == "pix-2"
        )
        assert (
            rows[0].gateway_api_key
            == "token-2"
        )


def test_falha_antes_do_commit_faz_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, application = _infra()

    application.salvar(
        provider="Mercado Pago",
        pix_key="pix-original",
        api_key="token-original",
    )

    def commit_com_falha(
        uow,
    ) -> None:
        uow.flush()

        raise RuntimeError(
            "falha_commit_gateway_e2e"
        )

    monkeypatch.setattr(
        legacy_gateway_teste_transacoes.UnitOfWorkV1,
        "commit",
        commit_com_falha,
    )

    with pytest.raises(
        RuntimeError,
        match="falha_commit_gateway_e2e",
    ):
        application.salvar(
            provider="Asaas",
            pix_key="pix-nao-persistir",
            api_key="token-nao-persistir",
        )

    with Session(engine) as session:
        row = (
            session.query(
                ConfiguracaoMetaTeste
            )
            .one()
        )

        assert (
            row.gateway_provider
            == "Mercado Pago"
        )
        assert (
            row.gateway_pix_key
            == "pix-original"
        )
        assert (
            row.gateway_api_key
            == "token-original"
        )
