"""Resolver local da franquia previamente autorizada pela autoridade comercial.

Não sincroniza orçamento na pergunta, não acessa serviços externos e não
permite habilitação sem entitlement vigente + ledger provisionado para a unidade.
O limite em USD é custo interno, jamais deve ser exposto na interface do cliente.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.ai_router import RotaIA, SolicitacaoIA
from infra.ai_budget_guard import PoliticaReservaIA
from infra.ai_budget_sqlalchemy import (
    FranquiaAIBudgetORM,
    OrcamentoIndisponivelIA,
)
from infra.comercial.entitlement_orm import KordenaEntitlementProjectionORM


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _positivo(value: object, *, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise OrcamentoIndisponivelIA(f"ia_politica_{field}_invalido") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise OrcamentoIndisponivelIA(f"ia_politica_{field}_invalido")
    return parsed


class ResolverPoliticaFranquiaLocal:
    """Verifica a projeção canônica do Command e o ledger transacional local."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._sessions = session_factory
        self._now = now

    def __call__(self, solicitacao: SolicitacaoIA, rota: RotaIA) -> PoliticaReservaIA:
        now = _utc(self._now())
        tenant = solicitacao.tenant_id
        unidade = solicitacao.unidade_id
        capability = solicitacao.capability.value
        key = f"ai.budget.{capability}"
        with self._sessions() as session:
            entitlement = session.get(KordenaEntitlementProjectionORM, tenant)
            if (
                entitlement is None
                or entitlement.tenant_id != tenant
                or entitlement.access_mode != "full"
                or entitlement.commercial_state not in {
                    "trial_active", "subscription_active", "internal_test"
                }
                or not (_utc(entitlement.effective_from) <= now
                        < _utc(entitlement.valid_until))
                or not entitlement.product_account_id
                or not entitlement.plan_version_id
            ):
                raise OrcamentoIndisponivelIA("ia_entitlement_nao_vigente")
            policy = entitlement.capabilities_json.get(key)
            if (
                not isinstance(policy, dict)
                or policy.get("enabled") is not True
                or policy.get("limit_unit") != "USD"
                or not isinstance(policy.get("config"), dict)
            ):
                raise OrcamentoIndisponivelIA("ia_capacidade_orcamento_nao_autorizada")
            limit = _positivo(policy.get("limit_value"), field="limite")
            max_per_request = _positivo(
                policy["config"].get("maximo_por_tentativa"),
                field="maximo_por_tentativa",
            )
            if max_per_request > limit:
                raise OrcamentoIndisponivelIA("ia_custo_por_chamada_excede_limite")

            matching = session.scalars(
                select(FranquiaAIBudgetORM).where(
                    FranquiaAIBudgetORM.tenant_id == tenant,
                    FranquiaAIBudgetORM.unidade_id == unidade,
                    FranquiaAIBudgetORM.capability == capability,
                )
            ).all()
            active = [
                row for row in matching
                if _utc(row.vigencia_inicio) <= now < _utc(row.vigencia_fim)
            ]
            if len(active) != 1:
                raise OrcamentoIndisponivelIA("ia_franquia_local_ausente_ou_ambigua")
            budget = active[0]
            if (
                budget.moeda != "USD"
                or budget.revisao_politica != entitlement.revision
                or budget.limite != limit
                or not budget.ciclo_id
            ):
                raise OrcamentoIndisponivelIA("ia_franquia_revisao_divergente")

            return PoliticaReservaIA(
                tenant_id=tenant,
                unidade_id=unidade,
                capability=capability,
                budget_id=budget.budget_id,
                ciclo_id=budget.ciclo_id,
                moeda="USD",
                maximo_por_tentativa=max_per_request,
            )
