"""Feature flag e acesso comercial do Delivery Próprio V1."""

from collections.abc import Iterable

from core.runtime.registry import module_v1_enabled
from core.seguranca.permissoes import Permissao


def delivery_v1_enabled() -> bool:
    """Libera Delivery somente com pedidos, pagamentos, entrega e autorização reais."""

    return module_v1_enabled(
        name="delivery",
        flag_env="FM_AI_DELIVERY_V1",
        required_adapters=("orders", "payments", "delivery", "auth"),
    )


def delivery_v1_access_allowed(permissoes: Iterable[Permissao]) -> bool:
    """Exige as capacidades mínimas para operar a superfície comercial."""

    disponiveis = frozenset(permissoes)
    return {
        Permissao.PEDIDO_CRIAR,
        Permissao.PEDIDO_VISUALIZAR,
        Permissao.CLIENTE_VISUALIZAR,
    }.issubset(disponiveis)
