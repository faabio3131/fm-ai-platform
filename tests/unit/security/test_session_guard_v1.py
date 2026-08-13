from __future__ import annotations

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase

from infra.seguranca.session_guard import (
    CommercialGuardedSession,
    SegredoLegadoEmTextoPuro,
    build_session_factory,
)


class Base(DeclarativeBase):
    pass


class ConfigLegada(Base):
    __tablename__ = "config_legada_teste"

    id = Column(Integer, primary_key=True)
    whatsapp_token = Column(String, nullable=True)
    gateway_api_key = Column(String, nullable=True)


def test_commercial_session_rejects_plaintext_secret() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine=engine, commercial=True)
    session = factory()
    try:
        assert isinstance(session, CommercialGuardedSession)
        session.add(ConfigLegada(id=1, whatsapp_token="secret-plain"))
        try:
            session.commit()
        except SegredoLegadoEmTextoPuro:
            session.rollback()
        else:  # pragma: no cover - proteção contra regressão
            raise AssertionError("segredo em texto puro foi persistido")
    finally:
        session.close()


def test_development_session_keeps_legacy_compatibility() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = build_session_factory(engine=engine, commercial=False)
    session = factory()
    try:
        session.add(ConfigLegada(id=1, whatsapp_token="dev-only"))
        session.commit()
        row = session.get(ConfigLegada, 1)
        assert row is not None
        assert row.whatsapp_token == "dev-only"
    finally:
        session.close()
