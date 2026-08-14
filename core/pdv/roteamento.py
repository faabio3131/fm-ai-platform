"""Roteamento fail-closed baseado apenas em configuracao confiavel do servidor."""

from dataclasses import dataclass, field
from enum import StrEnum

from core.pagamentos.flags import FlagsPagamentosV1
from core.pedidos.flags import OrdersFeatureFlags
from core.seguranca.contexto import ContextoExecucao


class ModoPDV(StrEnum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    AUTHORITATIVE_CANARY = "authoritative_canary"


class ConfiguracaoRolloutInvalida(RuntimeError):
    pass


@dataclass(frozen=True)
class PDVFlags:
    orders: OrdersFeatureFlags = field(default_factory=OrdersFeatureFlags)
    payments: FlagsPagamentosV1 = field(default_factory=FlagsPagamentosV1)
    stock_ledger_authoritative: bool = False


@dataclass(frozen=True)
class PDVRolloutConfig:
    tenant_id: str
    unidade_id: str
    terminais_permitidos: frozenset[str] = frozenset()
    modo: ModoPDV = ModoPDV.LEGACY
    flags: PDVFlags = field(default_factory=PDVFlags)
    contexto_confiavel: bool = False


def decidir_modo(
    *, contexto: ContextoExecucao, terminal_id: str, config: PDVRolloutConfig
) -> ModoPDV:
    if config.modo is ModoPDV.LEGACY:
        return ModoPDV.LEGACY
    if (
        contexto.tenant_id != config.tenant_id
        or contexto.unidade_id != config.unidade_id
    ):
        return ModoPDV.LEGACY
    if config.modo is ModoPDV.SHADOW:
        return (
            ModoPDV.SHADOW
            if config.flags.orders.orders_shadow_write
            and not config.flags.orders.orders_authoritative
            else ModoPDV.LEGACY
        )
    coerentes = (
        config.contexto_confiavel
        and terminal_id in config.terminais_permitidos
        and config.flags.orders.orders_authoritative
        and config.flags.payments.payments_v1_enabled
        and config.flags.payments.sales_from_orders_enabled
        and config.flags.payments.legacy_sale_adapter_enabled
        and config.flags.stock_ledger_authoritative
    )
    if not coerentes:
        raise ConfiguracaoRolloutInvalida("canary_incompleto_ou_nao_confiavel")
    return ModoPDV.AUTHORITATIVE_CANARY
