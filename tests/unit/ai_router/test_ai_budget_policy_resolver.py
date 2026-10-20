"""Acesso à IA depende da política comercial local e orçamento provisionado."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.ai_router import CapabilityIA, RotaIA, SolicitacaoIA
from infra.ai_budget_policy_resolver import ResolverPoliticaFranquiaLocal
from infra.ai_budget_sqlalchemy import (
    AIBudgetBase, LedgerFranquiasIASQLAlchemy, OrcamentoIndisponivelIA,
)
from infra.comercial.entitlement_orm import EntitlementBase, KordenaEntitlementProjectionORM

NOW = datetime(2026, 10, 18, 21, 0, tzinfo=timezone.utc)
POLICY_KEY = "ai.budget.tool_planning"


def _setup(tmp_path, *, enabled: bool = True, policy_version: int = 4):
    engine = create_engine(f"sqlite:///{tmp_path / 'policy.db'}")
    EntitlementBase.metadata.create_all(engine)
    AIBudgetBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory.begin() as session:
        session.add(KordenaEntitlementProjectionORM(
            tenant_id="tenant-a",
            product_account_id="account-a",
            revision=policy_version,
            commercial_state="subscription_active",
            plan_code="KORDENA_PLAN_A",
            plan_version_id="plan-a-v2",
            access_mode="full",
            capabilities_json={
                POLICY_KEY: {
                    "enabled": enabled,
                    "limit_value": "1.00",
                    "limit_unit": "USD",
                    "config": {"maximo_por_tentativa": "0.05", "scope": "unit"},
                },
            },
            effective_from=NOW - timedelta(days=1),
            valid_until=NOW + timedelta(days=25),
            last_synced_at=NOW,
        ))
    LedgerFranquiasIASQLAlchemy(factory).sincronizar_politica(
        budget_id="budget-a", tenant_id="tenant-a", unidade_id="unit-a",
        capability="tool_planning", ciclo_id="out-2026", moeda="USD",
        limite=Decimal("1.00"), revisao_politica=4,
        vigencia_inicio=NOW - timedelta(days=1),
        vigencia_fim=NOW + timedelta(days=25),
    )
    return factory


def _request(tenant="tenant-a", unit="unit-a") -> SolicitacaoIA:
    return SolicitacaoIA(
        tenant_id=tenant, unidade_id=unit,
        request_id="r1", correlation_id="c1",
        capability=CapabilityIA.TOOL_PLANNING,
        conteudo="teste",
    )


def _route() -> RotaIA:
    return RotaIA(
        configuracao_id="route-a", provider="openai", model="test-model",
        capability=CapabilityIA.TOOL_PLANNING, prioridade=100,
        price_snapshot_id="snapshot-a",
    )


def test_entitlement_local_vigente_resolve_orcamento_sem_command(tmp_path) -> None:
    factory = _setup(tmp_path)
    policy = ResolverPoliticaFranquiaLocal(factory, now=lambda: NOW)(
        _request(), _route()
    )
    assert policy.tenant_id == "tenant-a"
    assert policy.unidade_id == "unit-a"
    assert policy.capability == "tool_planning"
    assert policy.maximo_por_tentativa == Decimal("0.05")
    assert policy.revisao_politica == 4


@pytest.mark.parametrize(
    "tenant,unit",
    [("tenant-b", "unit-a"), ("tenant-a", "unit-b")],
)
def test_nao_empresta_orcamento_de_outro_escopo(tmp_path, tenant, unit) -> None:
    factory = _setup(tmp_path)
    with pytest.raises(OrcamentoIndisponivelIA):
        ResolverPoliticaFranquiaLocal(factory, now=lambda: NOW)(
            _request(tenant, unit), _route()
        )


def test_entitlement_revogado_falha_fechado(tmp_path) -> None:
    factory = _setup(tmp_path, enabled=False)
    with pytest.raises(OrcamentoIndisponivelIA):
        ResolverPoliticaFranquiaLocal(factory, now=lambda: NOW)(
            _request(), _route()
        )


def test_revisao_incompatível_bloqueia_nova_chamada(tmp_path) -> None:
    factory = _setup(tmp_path, policy_version=5)
    with pytest.raises(OrcamentoIndisponivelIA):
        ResolverPoliticaFranquiaLocal(factory, now=lambda: NOW)(
            _request(), _route()
        )


def test_expiracao_da_politica_nao_concede_mais_ia(tmp_path) -> None:
    factory = _setup(tmp_path)
    with pytest.raises(OrcamentoIndisponivelIA):
        ResolverPoliticaFranquiaLocal(
            factory, now=lambda: NOW + timedelta(days=40)
        )(_request(), _route())
