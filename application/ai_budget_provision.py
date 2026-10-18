"""Provisionamento local das franquias após evento comercial já confirmado.

A fonte dos direitos é a projeção canônica da assinatura, sincronizada pelo
Command; nenhuma pergunta ao modelo cria orçamento. As franquias são por
unidade explicitamente autorizada; não há concessão a tenant default/global.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from infra.ai_budget_sqlalchemy import (
    LedgerFranquiasIASQLAlchemy,
    OrcamentoIndisponivelIA,
)
from infra.comercial.entitlement_orm import KordenaEntitlementProjectionORM
from infra.comercial.subscription_orm import FMCommercialSubscriptionORM
from infra.seguranca.modelos_orm import (
    IdentityMembershipORM,
    IdentityMembershipUnitORM,
)

SessionFactory = Callable[[], Session]


def _utc(value: datetime | None) -> datetime:
    if value is None:
        raise OrcamentoIndisponivelIA("ia_ciclo_assinatura_incompleto")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _amount(value: object) -> Decimal:
    try:
        number = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise OrcamentoIndisponivelIA("ia_limite_comercial_invalido") from exc
    if not number.is_finite() or number <= 0:
        raise OrcamentoIndisponivelIA("ia_limite_comercial_invalido")
    return number


def provisionar_franquias_assinatura(
    session_factory: SessionFactory,
    *,
    tenant_id: str,
    product_account_id: str,
    subscription_id: str,
) -> int:
    """Provisiona exclusivamente capacidades `ai.budget.<capability>` aprovadas.

    Política de custo em USD por unidade precisa declarar `scope=unit`.
    Ausência de limite explícito significa franquia NÃO concedida.
    """
    with session_factory() as session:
        subscription = session.get(FMCommercialSubscriptionORM, subscription_id)
        entitlement = session.get(KordenaEntitlementProjectionORM, tenant_id)
        if (
            subscription is None
            or entitlement is None
            or subscription.tenant_id != tenant_id
            or subscription.product_account_id != product_account_id
            or entitlement.product_account_id != product_account_id
            or entitlement.tenant_id != tenant_id
            or subscription.status != "active"
            or entitlement.commercial_state != "subscription_active"
            or entitlement.access_mode != "full"
            or subscription.plan_version_id != entitlement.plan_version_id
        ):
            return 0

        start = _utc(subscription.current_period_start)
        end = _utc(subscription.current_period_end)
        if start >= end:
            raise OrcamentoIndisponivelIA("ia_ciclo_assinatura_invalido")
        grants = session.scalars(
            select(distinct(IdentityMembershipUnitORM.unidade_id))
            .join(
                IdentityMembershipORM,
                IdentityMembershipORM.membership_id == IdentityMembershipUnitORM.membership_id,
            ).where(
                IdentityMembershipORM.tenant_id == tenant_id,
                IdentityMembershipORM.product_code == "KORDENA",
                IdentityMembershipORM.ativo.is_(True),
            )
        ).all()
        units = sorted(set(grants))
        if not units:
            return 0

        configured = []
        caps = entitlement.capabilities_json
        if not isinstance(caps, dict):
            raise OrcamentoIndisponivelIA("ia_capacidades_comerciais_invalidas")
        for raw, entitlement_cap in caps.items():
            if not isinstance(raw, str) or not raw.startswith("ai.budget."):
                continue
            if not isinstance(entitlement_cap, dict):
                raise OrcamentoIndisponivelIA("ia_capacidade_comercial_invalida")
            if entitlement_cap.get("enabled") is not True:
                continue
            settings = entitlement_cap.get("config")
            if (
                entitlement_cap.get("limit_unit") != "USD"
                or not isinstance(settings, dict)
                or settings.get("scope") != "unit"
            ):
                raise OrcamentoIndisponivelIA("ia_escopo_franquia_nao_autorizado")
            ceiling = _amount(entitlement_cap.get("limit_value"))
            per_attempt = _amount(settings.get("maximo_por_tentativa"))
            if per_attempt > ceiling:
                raise OrcamentoIndisponivelIA("ia_custo_chamada_acima_da_franquia")
            capability = raw.removeprefix("ai.budget.")
            if not capability:
                raise OrcamentoIndisponivelIA("ia_capability_invalida")
            configured.append((capability, ceiling))

    ledger = LedgerFranquiasIASQLAlchemy(session_factory)
    count = 0
    ciclo_id = subscription_id + ":" + start.strftime("%Y%m%dT%H%M%S")
    for unit in units:
        for capability, maximum in configured:
            budget_id = hashlib.sha256(
                "|".join((tenant_id, unit, capability, ciclo_id)).encode("utf-8")
            ).hexdigest()
            ledger.sincronizar_politica(
                budget_id=budget_id,
                tenant_id=tenant_id,
                unidade_id=unit,
                capability=capability,
                ciclo_id=ciclo_id,
                moeda="USD",
                limite=maximum,
                revisao_politica=entitlement.revision,
                vigencia_inicio=start,
                vigencia_fim=end,
            )
            count += 1
    return count
