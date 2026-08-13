"""Alertas deterministas, informativos e sem efeitos colaterais."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .modelos import AlertaPedidoCentral, ResumoFinanceiroCentral


@dataclass(frozen=True)
class ConfiguracaoAlertas:
    sem_atualizacao_apos: timedelta = timedelta(hours=2)


def calcular_alertas(
    *,
    status: str,
    atualizado_em: datetime,
    financeiro: ResumoFinanceiroCentral,
    agora: datetime,
    configuracao: ConfiguracaoAlertas | None = None,
) -> tuple[AlertaPedidoCentral, ...]:
    config = configuracao if configuracao is not None else ConfiguracaoAlertas()
    if agora.utcoffset() is None:
        raise ValueError("agora deve ser timezone-aware")
    atualizado = (
        atualizado_em.replace(tzinfo=timezone.utc)
        if atualizado_em.utcoffset() is None
        else atualizado_em.astimezone(timezone.utc)
    )
    alertas: list[AlertaPedidoCentral] = []
    terminais = {"concluido", "cancelado"}
    if status not in terminais and financeiro.situacao in {"pendente", "parcial"}:
        alertas.append(
            AlertaPedidoCentral("PAGAMENTO_PENDENTE", "atencao", "Pagamento pendente")
        )
    if financeiro.reconciliacao_status == "divergente":
        alertas.append(
            AlertaPedidoCentral(
                "RECONCILIACAO_DIVERGENTE", "alta", "Reconciliação divergente"
            )
        )
    if (
        status not in terminais
        and agora.astimezone(timezone.utc) - atualizado >= config.sem_atualizacao_apos
    ):
        alertas.append(
            AlertaPedidoCentral(
                "PEDIDO_SEM_ATUALIZACAO", "atencao", "Pedido sem atualização"
            )
        )
    return tuple(alertas)
