"""Feature flag do KDS V1."""

from collections.abc import Collection

from core.runtime.registry import module_v1_enabled
from core.seguranca.permissoes import Permissao


def kds_v1_enabled() -> bool:
    """Libera KDS somente quando pedidos, KDS e autorização reais estiverem prontos."""

    return module_v1_enabled(
        name="kds",
        flag_env="FM_AI_KDS_V1",
        required_adapters=("orders", "kds", "auth"),
    )


def kds_v1_access_allowed(permissoes: Collection[Permissao]) -> bool:
    """Libera a superfície KDS somente a quem pode visualizar produção."""

    return (
        kds_v1_enabled()
        and Permissao.PRODUCAO_VISUALIZAR in permissoes
    )
