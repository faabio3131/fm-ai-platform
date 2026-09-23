"""Gate de acesso comercial do Kordena — KCA-11.

A autoridade continua sendo a projeção local de entitlement produzida pela
FM Commercial Platform. O rollout é explícito para preservar a compatibilidade
com tenants V1 ainda não vinculados ao Commercial Registry antes do KCA-17.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from application.commercial_entitlement import AplicacaoEntitlementComercialV1
from core.comercial.entitlement import ModoAcessoComercial
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
