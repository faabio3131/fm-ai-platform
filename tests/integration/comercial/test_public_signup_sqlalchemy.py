from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.public_signup import AplicacaoPublicSignupV1, SignupVerificationError
from core.comercial.signup import EstadoSignup
from core.seguranca.segredos import ReferenceSecretStore
from infra.comercial.signup_orm import FMPublicSignupIntentORM
from migrations.runner import run_migrations

KEY = "obShALmcxtf1vGcUP3xIs6mVnxov9bHzsOSQ_r9SXI4="
PASSWORD = "Senha-Segura-KCA06-123"


def _factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _app(factory, **kwargs):
    return AplicacaoPublicSignupV1(
        factory,
        secret_store=ReferenceSecretStore(mapping={"signup": KEY}),
        credential_secret_reference="mapping:signup",
        **kwargs,
    )


def _create(app, email="novo@example.com"):
    return app.criar_intencao(
        owner_name="Responsável Teste",
        owner_email=email,
        owner_password=PASSWORD,
        primary_contact_phone="+5511999999999",
        establishment_name="Restaurante Teste",
        segment="restaurante",
        terms_accepted=True,
        consent_json={"marketing": False},
        correlation_id="corr-kca06",
    )


def test_signup_persiste_token_hash_e_credencial_cifrada() -> None:
    factory = _factory()
    app = _app(factory)
    created = _create(app)
    with factory() as session:
        row = session.get(FMPublicSignupIntentORM, created.signup.signup_id)
        assert row is not None
        assert row.credential_ciphertext
        assert PASSWORD not in row.credential_ciphertext
        assert created.verification_token not in row.verification_token_sha256
        assert len(row.verification_token_sha256) == 64


def test_verificacao_provisiona_e_remove_credencial_transitoria() -> None:
    factory = _factory()
    app = _app(factory)
    created = _create(app)
    ready = app.verificar_e_provisionar(
        signup_id=created.signup.signup_id,
        verification_token=created.verification_token,
    )
    assert ready.status == EstadoSignup.READY
    assert ready.provisioning_id
    assert ready.credential_ciphertext is None
    with pytest.raises(SignupVerificationError, match="already_used"):
        app.verificar_e_provisionar(
            signup_id=created.signup.signup_id,
            verification_token=created.verification_token,
        )


def test_token_expirado_falha_fechado() -> None:
    factory = _factory()
    app = _app(factory)
    created = _create(app)
    with factory() as session, session.begin():
        row = session.get(FMPublicSignupIntentORM, created.signup.signup_id)
        assert row is not None
        row.verification_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with pytest.raises(SignupVerificationError, match="expired"):
        app.verificar_e_provisionar(
            signup_id=created.signup.signup_id,
            verification_token=created.verification_token,
        )


def test_reenvio_rotaciona_token() -> None:
    factory = _factory()
    app = _app(factory, resend_cooldown_seconds=0)
    created = _create(app)
    resent = app.reenviar_token(signup_id=created.signup.signup_id)
    assert resent.verification_token != created.verification_token
    with pytest.raises(SignupVerificationError):
        app.verificar_e_provisionar(
            signup_id=created.signup.signup_id,
            verification_token=created.verification_token,
        )
