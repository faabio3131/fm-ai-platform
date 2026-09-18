from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra.fiscal.modelos_orm import FiscalBase
from infra.fiscal.perfis_sqlalchemy import (
    FiscalIssuerProfileStoreSQLAlchemy,
    FiscalProductProfileStoreSQLAlchemy,
    FiscalProfileConflictError,
    FiscalProfileNotFoundError,
    FiscalProfileOverlapError,
)
from kordena_fiscal.domain import (
    BrazilianJurisdiction,
    CnaeCode,
    Cnpj,
    ExecutionScope,
    FiscalAddress,
    FiscalEnvironment,
    FiscalProductProfile,
    FiscalProfile,
    FiscalUnitCode,
    Gtin,
    NcmCode,
    ProductOrigin,
    StateRegistration,
    TaxClassificationHints,
    TaxRegimeCode,
)

NOW = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    FiscalBase.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _scope(
    *,
    tenant: str = "tenant-a",
    unit: str = "unit-a",
    environment: FiscalEnvironment = FiscalEnvironment.HOMOLOGATION,
    correlation: str = "corr-a",
) -> ExecutionScope:
    return ExecutionScope(
        tenant_id=tenant,
        unit_id=unit,
        environment=environment,
        correlation_id=correlation,
    )


def _issuer(
    *,
    scope: ExecutionScope | None = None,
    version: int = 1,
    effective_from: datetime = NOW - timedelta(days=10),
    effective_to: datetime | None = None,
    legal_name: str = "Kordena Teste Ltda",
) -> FiscalProfile:
    active_scope = scope or _scope()
    return FiscalProfile(
        profile_id=f"issuer-{version}",
        scope=active_scope,
        cnpj=Cnpj("11222333000181"),
        legal_name=legal_name,
        tax_regime=TaxRegimeCode.SIMPLES_NACIONAL,
        state_registration=StateRegistration(
            state_code="SP",
            number="110042490114",
        ),
        primary_cnae=CnaeCode("5611201"),
        address=FiscalAddress(
            street="Rua Teste",
            number="100",
            district="Centro",
            municipality_name="Sao Paulo",
            jurisdiction=BrazilianJurisdiction("SP", "3550308"),
            postal_code="01001000",
        ),
        effective_from=effective_from,
        effective_to=effective_to,
        version=version,
        trade_name="Kordena",
    )


def _product(
    *,
    scope: ExecutionScope | None = None,
    product_id: str = "42",
    version: int = 1,
    effective_from: datetime = NOW - timedelta(days=10),
    effective_to: datetime | None = None,
    description: str = "X-Burger",
) -> FiscalProductProfile:
    active_scope = scope or _scope()
    return FiscalProductProfile(
        profile_id=f"product-{product_id}-{version}",
        product_id=product_id,
        scope=active_scope,
        commercial_code=f"P{product_id}",
        description=description,
        ncm=NcmCode("21069090"),
        commercial_unit=FiscalUnitCode("UN"),
        taxable_unit=FiscalUnitCode("UN"),
        origin=ProductOrigin.NATIONAL,
        effective_from=effective_from,
        effective_to=effective_to,
        version=version,
        gtin=Gtin("SEM GTIN"),
        hints=TaxClassificationHints(
            ibs_cbs_classification_code="FOOD.TEST",
        ),
    )


def test_wp031d_issuer_profile_is_durable_replay_safe_and_reference_only() -> None:
    sessions = _factory()
    store = FiscalIssuerProfileStoreSQLAlchemy(sessions)
    profile = _issuer()

    saved = store.save(
        profile,
        certificate_reference="vault://fiscal/cert-a",
        provider_config_id="integration:fiscal:a",
    )
    replay = store.save(
        profile,
        certificate_reference="vault://fiscal/cert-a",
        provider_config_id="integration:fiscal:a",
    )
    resolved = store.resolve(scope=_scope(correlation="corr-runtime"), issued_at=NOW)
    references = store.references(scope=_scope(), version=1)

    assert saved == replay == profile
    assert resolved.profile_id == profile.profile_id
    assert resolved.scope.correlation_id == "corr-runtime"
    assert resolved.cnpj == profile.cnpj
    assert references == ("vault://fiscal/cert-a", "integration:fiscal:a")


def test_wp031d_issuer_profile_version_conflict_and_overlap_fail_closed() -> None:
    sessions = _factory()
    store = FiscalIssuerProfileStoreSQLAlchemy(sessions)
    store.save(_issuer())

    with pytest.raises(FiscalProfileConflictError):
        store.save(_issuer(legal_name="Outra Razao Social"))

    with pytest.raises(FiscalProfileOverlapError):
        store.save(
            _issuer(
                version=2,
                effective_from=NOW - timedelta(days=1),
            )
        )


def test_wp031d_issuer_profile_effective_dating_selects_exact_version() -> None:
    sessions = _factory()
    store = FiscalIssuerProfileStoreSQLAlchemy(sessions)
    split = NOW - timedelta(days=2)
    store.save(
        _issuer(
            version=1,
            effective_from=NOW - timedelta(days=20),
            effective_to=split,
        )
    )
    store.save(
        _issuer(
            version=2,
            effective_from=split,
            legal_name="Kordena Atual Ltda",
        )
    )

    old = store.resolve(
        scope=_scope(correlation="corr-old"),
        issued_at=NOW - timedelta(days=3),
    )
    current = store.resolve(scope=_scope(correlation="corr-current"), issued_at=NOW)

    assert old.version == 1
    assert current.version == 2
    assert current.legal_name == "Kordena Atual Ltda"


def test_wp031d_issuer_scope_and_environment_are_isolated() -> None:
    sessions = _factory()
    store = FiscalIssuerProfileStoreSQLAlchemy(sessions)
    store.save(_issuer())

    with pytest.raises(FiscalProfileNotFoundError):
        store.resolve(
            scope=_scope(tenant="tenant-b"),
            issued_at=NOW,
        )
    with pytest.raises(FiscalProfileNotFoundError):
        store.resolve(
            scope=_scope(
                environment=FiscalEnvironment.PRODUCTION,
                correlation="corr-prod",
            ),
            issued_at=NOW,
        )


def test_wp031d_product_binding_preserves_canonical_product_id() -> None:
    sessions = _factory()
    store = FiscalProductProfileStoreSQLAlchemy(sessions)
    profile = _product(product_id="42")

    saved = store.save(profile)
    replay = store.save(profile)
    resolved = store.resolve(
        scope=_scope(correlation="corr-sale"),
        product_id="42",
        issued_at=NOW,
    )

    assert saved == replay == profile
    assert resolved.product_id == "42"
    assert resolved.scope.correlation_id == "corr-sale"
    assert resolved.ncm.value == "21069090"
    assert resolved.hints.ibs_cbs_classification_code == "FOOD.TEST"


def test_wp031d_product_binding_conflict_overlap_and_missing_fail_closed() -> None:
    sessions = _factory()
    store = FiscalProductProfileStoreSQLAlchemy(sessions)
    store.save(_product())

    with pytest.raises(FiscalProfileConflictError):
        store.save(_product(description="Descricao divergente"))

    with pytest.raises(FiscalProfileOverlapError):
        store.save(
            _product(
                version=2,
                effective_from=NOW - timedelta(days=1),
            )
        )

    with pytest.raises(FiscalProfileNotFoundError):
        store.resolve(
            scope=_scope(),
            product_id="produto-sem-perfil",
            issued_at=NOW,
        )


def test_wp031d_product_binding_environment_isolated_without_second_catalog() -> None:
    sessions = _factory()
    store = FiscalProductProfileStoreSQLAlchemy(sessions)
    store.save(_product())

    with pytest.raises(FiscalProfileNotFoundError):
        store.resolve(
            scope=_scope(
                environment=FiscalEnvironment.PRODUCTION,
                correlation="corr-prod",
            ),
            product_id="42",
            issued_at=NOW,
        )
