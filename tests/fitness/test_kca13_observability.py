from __future__ import annotations

import inspect

import application.commercial_observability as observability
import application.fmcc_commercial_projection as fmcc_projection
import application.commercial_provisioning as commercial_provisioning
import application.public_signup as public_signup


def test_kca13_observability_is_read_only_and_reuses_existing_authorities() -> None:
    source = inspect.getsource(observability)

    assert "from sqlalchemy import select" in source
    assert "insert(" not in source
    assert "update(" not in source
    assert "delete(" not in source
    assert "AIFinOpsDailyORM" in source
    assert "CommercialAuditORM" in source
    assert "FMCommercialTrialORM" in source
    assert "FMCommercialSubscriptionORM" in source
    assert "FMBillingTransactionORM" in source


def test_kca13_excludes_internal_test_and_does_not_invent_infra_cost() -> None:
    source = inspect.getsource(observability)

    assert 'FMCustomerORM.account_class != "internal_test"' in source
    assert '"infrastructure_cost_source_not_configured"' in source
    assert '"risk_score": None' in source
    assert '"fx": "not_applied_multi_currency_kept_separate"' in source


def test_kca13_is_additive_to_kca12_contract() -> None:
    source = inspect.getsource(fmcc_projection)

    assert 'SCHEMA_VERSION = "kordena.fmcc.commercial.v1"' in source
    assert '"observability": observability' in source
    assert "AplicacaoCommercialObservabilityKCA13" in source


def test_kca13_public_signup_cannot_create_internal_test_customer() -> None:
    signup_source = inspect.getsource(public_signup.AplicacaoPublicSignupV1.verificar_e_provisionar)
    provisioning_source = inspect.getsource(
        commercial_provisioning.AplicacaoProvisioningKordenaV1._ensure_customer
    )

    assert "self._provisioning.solicitar" in signup_source
    assert "account_class=ClasseContaComercial.TRIAL" in provisioning_source
    assert "INTERNAL_TEST" not in provisioning_source
