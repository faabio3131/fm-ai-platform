"""Gate de acesso comercial do Kordena — KCA-11.

A autoridade continua sendo a projeção local de entitlement produzida pela
FM Commercial Platform. O rollout é explícito para preservar a compatibilidade
com tenants V1 ainda não vinculados ao Commercial Registry antes do KCA-17.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from application.commercial_subscription import AplicacaoSubscriptionComercialV1
from core.comercial.catalogo import StatusConfiguracaoCatalogo, utc as catalog_utc
from core.comercial.entitlement import ModoAcessoComercial
from infra.comercial.catalogo_sqlalchemy import RepositorioCatalogoComercialSQLAlchemy
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy


@dataclass(frozen=True, kw_only=True)
class StatusAcessoComercial:
    tenant_id: str
    enforcement_enabled: bool
    managed: bool
    product_account_id: str | None
    operational_allowed: bool
    entitled: bool
    access_mode: ModoAcessoComercial | None
    reason: str
    revision: int | None
    stale: bool


@dataclass(frozen=True, kw_only=True)
class OfertaPrecoComercial:
    price_id: str
    currency: str
    billing_period: str
    amount: Decimal


@dataclass(frozen=True, kw_only=True)
class OfertaPlanoComercial:
    plan_code: str
    rank: int
    plan_version_id: str
    display_name: str
    description: str | None
    marketing_badge: str | None
    prices: tuple[OfertaPrecoComercial, ...]


class AplicacaoAcessoComercialV1:
    """Resolve o acesso operacional sem criar uma segunda autoridade."""

    def __init__(
        self,
        session_factory,
        *,
        enforcement_enabled: bool,
        stale_grace_seconds: int = 300,
    ) -> None:
        self._session_factory = session_factory
        self._enforcement_enabled = enforcement_enabled
        self._entitlement = AplicacaoEntitlementComercialV1(
            session_factory,
            stale_grace_seconds=stale_grace_seconds,
        )

    def avaliar(
        self,
        *,
        tenant_id: str,
        agora: datetime | None = None,
    ) -> StatusAcessoComercial:
        tenant = tenant_id.strip()
        if not tenant:
            return StatusAcessoComercial(
                tenant_id="",
                enforcement_enabled=self._enforcement_enabled,
                managed=False,
                product_account_id=None,
                operational_allowed=False,
                entitled=False,
                access_mode=ModoAcessoComercial.BLOCKED,
                reason="tenant_missing",
                revision=None,
                stale=False,
            )

        with self._session_factory() as session:
            account = RepositorioComercialSQLAlchemy(
                session
            ).obter_conta_produto_por_tenant(
                product_code="KORDENA",
                product_tenant_id=tenant,
            )

        if account is None:
            allowed = not self._enforcement_enabled
            return StatusAcessoComercial(
                tenant_id=tenant,
                enforcement_enabled=self._enforcement_enabled,
                managed=False,
                product_account_id=None,
                operational_allowed=allowed,
                entitled=False,
                access_mode=None if allowed else ModoAcessoComercial.BLOCKED,
                reason=(
                    "commercial_gate_disabled_legacy_unmanaged"
                    if allowed
                    else "product_account_missing"
                ),
                revision=None,
                stale=False,
            )

        decision = self._entitlement.avaliar_local(
            tenant_id=tenant,
            product_account_id=account.product_account_id,
            agora=agora,
        )
        return StatusAcessoComercial(
            tenant_id=tenant,
            enforcement_enabled=self._enforcement_enabled,
            managed=True,
            product_account_id=account.product_account_id,
            operational_allowed=(
                decision.allowed or not self._enforcement_enabled
            ),
            entitled=decision.allowed,
            access_mode=decision.access_mode,
            reason=(
                decision.reason
                if self._enforcement_enabled or decision.allowed
                else f"commercial_gate_disabled:{decision.reason}"
            ),
            revision=decision.revision,
            stale=decision.stale,
        )

    def listar_ofertas(
        self,
        *,
        agora: datetime | None = None,
    ) -> tuple[OfertaPlanoComercial, ...]:
        instante = catalog_utc(agora) if agora is not None else catalog_utc(datetime.now().astimezone())
        with self._session_factory() as session:
            repo = RepositorioCatalogoComercialSQLAlchemy(session)
            ofertas: list[OfertaPlanoComercial] = []
            for plan in repo.listar_planos(product_code="KORDENA"):
                version = repo.versao_efetiva_plano(
                    plan_id=plan.plan_id,
                    instante=instante,
                )
                if version is None:
                    continue
                prices = tuple(
                    OfertaPrecoComercial(
                        price_id=price.price_id,
                        currency=price.currency,
                        billing_period=price.billing_period,
                        amount=price.amount,
                    )
                    for price in repo.listar_precos_versao(
                        plan_version_id=version.plan_version_id
                    )
                    if price.status == StatusConfiguracaoCatalogo.PUBLISHED
                    and price.valid_from is not None
                    and price.valid_from <= instante
                    and (price.valid_until is None or price.valid_until > instante)
                )
                if not prices:
                    continue
                ofertas.append(
                    OfertaPlanoComercial(
                        plan_code=plan.plan_code,
                        rank=plan.rank,
                        plan_version_id=version.plan_version_id,
                        display_name=version.display_name,
                        description=version.description,
                        marketing_badge=version.marketing_badge,
                        prices=prices,
                    )
                )
            return tuple(sorted(ofertas, key=lambda item: item.rank))

    def obter_assinatura(self, *, tenant_id: str):
        status = self.avaliar(tenant_id=tenant_id)
        if status.product_account_id is None:
            return None
        return AplicacaoSubscriptionComercialV1(
            self._session_factory
        ).obter_por_product_account(
            product_account_id=status.product_account_id,
        )
