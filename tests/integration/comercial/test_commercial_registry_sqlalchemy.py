from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.comercial_registry import AplicacaoCommercialRegistryV1
from core.comercial.erros import (
    ConflitoConcorrenciaComercial,
    ConflitoIdempotenciaComercial,
    RegistroComercialDuplicado,
)
from core.comercial.modelos import (
    ClasseContaComercial,
    StatusClienteComercial,
    StatusContaProduto,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.comercial.modelos_orm import CommercialAuditORM, CommercialOutboxORM
from migrations.runner import run_migrations


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory, AplicacaoCommercialRegistryV1(factory)


def _contexto(correlation_id: str = "kca01-corr") -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="internal-fm",
        unidade_id="internal-fm-hq",
        usuario_id="director-test",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id=correlation_id,
        solicitado_em=datetime.now(timezone.utc),
        origem="kca01-test",
        unidades_permitidas=frozenset({"internal-fm-hq"}),
    )


def _customer(app: AplicacaoCommercialRegistryV1, key: str = "customer-key"):
    return app.criar_cliente(
        contexto=_contexto(),
        idempotency_key=key,
        display_name="Restaurante Teste",
        legal_name=None,
        account_class=ClasseContaComercial.INTERNAL_TEST,
        primary_contact_email="Owner@Teste.COM",
        primary_contact_phone="+55 11 99999-0000",
    )


def test_customer_create_e_retry_sao_idempotentes_e_auditados() -> None:
    _, factory, app = _infra()

    primeiro = _customer(app)
    segundo = _customer(app)

    assert primeiro == segundo
    assert primeiro.primary_contact_email == "owner@teste.com"
    assert primeiro.customer_code.startswith("FMC-")
    assert primeiro.account_class == ClasseContaComercial.INTERNAL_TEST

    with factory() as session:
        auditorias = session.scalars(select(CommercialAuditORM)).all()
        outbox = session.scalars(select(CommercialOutboxORM)).all()

    assert len(auditorias) == 1
    assert auditorias[0].action == "commercial.customer.create"
    assert auditorias[0].metadata_safe["account_class"] == "internal_test"
    assert "owner@teste.com" not in str(auditorias[0].metadata_safe)

    assert len(outbox) == 1
    assert outbox[0].event_type == "customer.created"
    assert outbox[0].fm_customer_id == primeiro.fm_customer_id


def test_reuso_da_mesma_idempotency_key_com_payload_diferente_falha() -> None:
    _, _, app = _infra()
    _customer(app)

    with pytest.raises(ConflitoIdempotenciaComercial):
        app.criar_cliente(
            contexto=_contexto(),
            idempotency_key="customer-key",
            display_name="Outro Restaurante",
            legal_name=None,
            account_class=ClasseContaComercial.INTERNAL_TEST,
            primary_contact_email="owner@teste.com",
            primary_contact_phone=None,
        )


def test_update_customer_usa_optimistic_versioning() -> None:
    _, _, app = _infra()
    customer = _customer(app)

    atualizado = app.atualizar_cliente(
        contexto=_contexto(),
        fm_customer_id=customer.fm_customer_id,
        expected_version=1,
        display_name="Restaurante Teste Atualizado",
        legal_name="Razao Teste LTDA",
        status=StatusClienteComercial.ACTIVE,
        account_class=ClasseContaComercial.INTERNAL_TEST,
        primary_contact_email="owner@teste.com",
        primary_contact_phone=None,
    )
    assert atualizado.version == 2

    with pytest.raises(ConflitoConcorrenciaComercial):
        app.atualizar_cliente(
            contexto=_contexto(),
            fm_customer_id=customer.fm_customer_id,
            expected_version=1,
            display_name="Atualizacao concorrente",
            legal_name=None,
            status=StatusClienteComercial.ACTIVE,
            account_class=ClasseContaComercial.INTERNAL_TEST,
            primary_contact_email="owner@teste.com",
            primary_contact_phone=None,
        )


def test_product_account_idempotente_ativa_somente_com_tenant() -> None:
    _, _, app = _infra()
    customer = _customer(app)

    primeira = app.criar_conta_produto(
        contexto=_contexto(),
        idempotency_key="pa-key",
        fm_customer_id=customer.fm_customer_id,
        product_code="kordena",
    )
    segunda = app.criar_conta_produto(
        contexto=_contexto(),
        idempotency_key="pa-key",
        fm_customer_id=customer.fm_customer_id,
        product_code="KORDENA",
    )
    assert primeira == segunda
    assert primeira.status == StatusContaProduto.REQUESTED
    assert primeira.product_code == "KORDENA"

    ativa = app.transicionar_conta_produto(
        contexto=_contexto(),
        product_account_id=primeira.product_account_id,
        expected_version=1,
        status=StatusContaProduto.ACTIVE,
        product_tenant_id="tenant-kordena-1",
    )
    assert ativa.status == StatusContaProduto.ACTIVE
    assert ativa.product_tenant_id == "tenant-kordena-1"
    assert ativa.version == 2


def test_product_tenant_nao_pode_ser_reutilizado_por_outra_conta() -> None:
    _, _, app = _infra()
    customer_a = _customer(app, "customer-a")
    customer_b = app.criar_cliente(
        contexto=_contexto(),
        idempotency_key="customer-b",
        display_name="Cliente B",
        legal_name=None,
        account_class=ClasseContaComercial.TRIAL,
        primary_contact_email="b@example.com",
        primary_contact_phone=None,
    )

    account_a = app.criar_conta_produto(
        contexto=_contexto(),
        idempotency_key="pa-a",
        fm_customer_id=customer_a.fm_customer_id,
        product_code="KORDENA",
        product_tenant_id="tenant-unico",
    )
    assert account_a.product_tenant_id == "tenant-unico"

    with pytest.raises(RegistroComercialDuplicado):
        app.criar_conta_produto(
            contexto=_contexto(),
            idempotency_key="pa-b",
            fm_customer_id=customer_b.fm_customer_id,
            product_code="KORDENA",
            product_tenant_id="tenant-unico",
        )
