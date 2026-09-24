from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.comercial_registry import AplicacaoCommercialRegistryV1
from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from application.commercial_provisioning import AplicacaoProvisioningKordenaV1
from core.comercial.entitlement import ModoAcessoComercial
from core.comercial.erros import ConflitoIdempotenciaComercial
from core.comercial.modelos import StatusContaProduto
from core.comercial.provisioning import EstadoProvisionamento
from infra.administracao.modelos_orm import EmpresaAdminORM, UnidadeAdminORM
from infra.comercial.catalogo_orm import FMCommercialPlanORM, FMCommercialPlanVersionORM
from infra.comercial.modelos_orm import CommercialOutboxORM
from infra.comercial.provisioning_orm import FMCommercialProvisioningSagaORM
from infra.legacy_product_scope import resolver_loja_id_legada
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations


PASSWORD = "Senha-KCA05-Segura-123!"


def _factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with factory() as session, session.begin():
        plan = session.scalar(
            select(FMCommercialPlanORM).where(
                FMCommercialPlanORM.plan_code == "KORDENA_PLAN_A"
            )
        )
        assert plan is not None
        plan.status = "configured"
        plan.version = 2
        plan.updated_at = now
        session.add(
            FMCommercialPlanVersionORM(
                plan_version_id="kca05-trial-plan-version",
                plan_id=plan.plan_id,
                version_number=1,
                display_name="Plano fixture KCA-05",
                description=None,
                trial_eligible=True,
                marketing_badge=None,
                metadata_json={},
                status="published",
                valid_from=now - timedelta(days=1),
                valid_until=None,
                change_reason="fixture provisioning",
                created_by="test",
                validated_by="test",
                published_by="test",
                created_at=now,
                validated_at=now,
                published_at=now,
            )
        )
    return factory


def _request(app: AplicacaoProvisioningKordenaV1, key: str = "prov-1"):
    return app.solicitar(
        idempotency_key=key,
        owner_email="OWNER.KCA05@example.com",
        owner_password=PASSWORD,
        display_name="Restaurante KCA05",
        primary_contact_phone="+55 11 99999-0000",
        correlation_id=f"corr-{key}",
    )


def test_happy_path_provisiona_autoridades_com_trial_engine_kca07() -> None:
    factory = _factory()
    app = AplicacaoProvisioningKordenaV1(factory)
    requested = _request(app)
    ready = app.executar(
        provisioning_id=requested.provisioning_id,
        owner_password=PASSWORD,
    )

    assert ready.status == EstadoProvisionamento.READY
    assert ready.fm_customer_id
    assert ready.product_account_id
    assert ready.identity_user_id
    assert ready.membership_id
    assert ready.trial_binding_status == "active"
    assert ready.entitlement_snapshot_id

    account = AplicacaoCommercialRegistryV1(factory).obter_conta_produto(
        product_account_id=str(ready.product_account_id)
    )
    assert account.status == StatusContaProduto.ACTIVE
    assert account.product_tenant_id == ready.tenant_id

    with factory() as session:
        assert session.get(EmpresaAdminORM, ready.tenant_id) is not None
        assert session.get(
            UnidadeAdminORM, (ready.tenant_id, ready.unidade_id)
        ) is not None
        legacy_store_id = resolver_loja_id_legada(
            session,
            tenant_id=ready.tenant_id,
            unidade_id=ready.unidade_id,
        )
        assert legacy_store_id > 0
        identity = RepositorioIdentidadesSQLAlchemy(session).obter_por_email(
            "owner.kca05@example.com"
        )
        assert identity is not None
        memberships = RepositorioIdentidadesSQLAlchemy(session).listar_memberships(
            identity_user_id=str(identity.global_identity_id)
        )
        assert any(
            item.tenant_id == ready.tenant_id and item.product_code == "KORDENA"
            for item in memberships
        )
        event_types = set(session.scalars(select(CommercialOutboxORM.event_type)))
    assert "tenant.provisioning_requested" in event_types
    assert "tenant.provisioned" in event_types
    assert "entitlement.changed" in event_types

    decision = AplicacaoEntitlementComercialV1(factory).avaliar_local(
        tenant_id=ready.tenant_id,
        product_account_id=str(ready.product_account_id),
    )
    assert decision.allowed is True
    assert decision.access_mode == ModoAcessoComercial.FULL


def test_solicitacao_e_execucao_sao_idempotentes() -> None:
    factory = _factory()
    app = AplicacaoProvisioningKordenaV1(factory)
    first = _request(app, "same-key")
    repeated = _request(app, "same-key")
    assert repeated.provisioning_id == first.provisioning_id

    ready = app.executar(
        provisioning_id=first.provisioning_id,
        owner_password=PASSWORD,
    )
    again = app.executar(
        provisioning_id=first.provisioning_id,
        owner_password=PASSWORD,
    )
    assert again == ready

    with pytest.raises(
        ConflitoIdempotenciaComercial,
        match="provisioning_idempotency_payload_conflict",
    ):
        app.solicitar(
            idempotency_key="same-key",
            owner_email="other@example.com",
            owner_password=PASSWORD,
            display_name="Outro",
            primary_contact_phone=None,
            correlation_id="corr-other",
        )


@pytest.mark.parametrize(
    "failure_step",
    [
        "validating",
        "customer",
        "product_account",
        "product_account_provisioning",
        "identity_membership",
        "admin_scope",
        "activate_product_account",
        "trial",
        "ready",
    ],
)
def test_falha_retryable_e_restart_retomam_sem_duplicar(
    failure_step: str,
) -> None:
    factory = _factory()
    fired = False

    def fail_once(step: str) -> None:
        nonlocal fired
        if step == failure_step and not fired:
            fired = True
            raise TimeoutError(f"injected:{step}")

    failing = AplicacaoProvisioningKordenaV1(factory, failure_hook=fail_once)
    requested = _request(failing, f"retry-{failure_step}")
    with pytest.raises(TimeoutError, match="injected"):
        failing.executar(
            provisioning_id=requested.provisioning_id,
            owner_password=PASSWORD,
        )

    with factory() as session:
        persisted = session.get(
            FMCommercialProvisioningSagaORM, requested.provisioning_id
        )
        assert persisted is not None
        assert persisted.status == EstadoProvisionamento.FAILED_RETRYABLE.value

    resumed = AplicacaoProvisioningKordenaV1(factory).executar(
        provisioning_id=requested.provisioning_id,
        owner_password=PASSWORD,
    )
    assert resumed.status == EstadoProvisionamento.READY
    assert resumed.attempts == 2


def test_compensacao_logica_preserva_evidencia_e_fecha_product_account() -> None:
    factory = _factory()

    def fail_admin(step: str) -> None:
        if step == "admin_scope":
            raise RuntimeError("admin_scope_indisponivel")

    app = AplicacaoProvisioningKordenaV1(factory, failure_hook=fail_admin)
    requested = _request(app, "compensate")
    with pytest.raises(RuntimeError, match="admin_scope_indisponivel"):
        app.executar(
            provisioning_id=requested.provisioning_id,
            owner_password=PASSWORD,
        )

    compensated = AplicacaoProvisioningKordenaV1(factory).compensar(
        provisioning_id=requested.provisioning_id,
        motivo="teste de compensacao",
    )
    assert compensated.status == EstadoProvisionamento.COMPENSATED
    assert compensated.fm_customer_id
    assert compensated.product_account_id

    account = AplicacaoCommercialRegistryV1(factory).obter_conta_produto(
        product_account_id=str(compensated.product_account_id)
    )
    assert account.status == StatusContaProduto.CLOSED


def test_inbox_de_provisioning_deduplica_evento() -> None:
    factory = _factory()
    app = AplicacaoProvisioningKordenaV1(factory)
    requested = _request(app, "inbox")
    assert app.registrar_evento(
        event_id="evt-kca05",
        provisioning_id=requested.provisioning_id,
        event_type="dependency.ready",
    )
    assert not app.registrar_evento(
        event_id="evt-kca05",
        provisioning_id=requested.provisioning_id,
        event_type="dependency.ready",
    )


def test_saga_nao_persiste_password_em_claro() -> None:
    factory = _factory()
    app = AplicacaoProvisioningKordenaV1(factory)
    requested = _request(app, "no-secret")
    with factory() as session:
        row = session.get(FMCommercialProvisioningSagaORM, requested.provisioning_id)
        assert row is not None
        rendered = " ".join(str(value) for value in row.__dict__.values())
        assert PASSWORD not in rendered
