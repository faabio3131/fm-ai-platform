"""Modelo consultavel e detector conservador de divergencias do checkout."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class StatusReconciliacao(StrEnum):
    CONCILIADO = "conciliado"
    DIVERGENTE = "divergente"
    REPARO_NECESSARIO = "reparo_necessario"


@dataclass(frozen=True, kw_only=True)
class ReconciliacaoPDV:
    tenant_id: str
    unidade_id: str
    modo: str
    idempotency_key: str
    criado_em: datetime
    pedido_id: str | None = None
    pagamento_id: str | None = None
    venda_financeira_id: str | None = None
    venda_legada_id: str | None = None
    valor_pedido: Decimal | None = None
    valor_pagamento: Decimal | None = None
    valor_venda_financeira: Decimal | None = None
    valor_venda_legada: Decimal | None = None
    estoque_estrategia: str = "legado"
    cashback_usado: Decimal = Decimal(0)
    cashback_ganho: Decimal = Decimal(0)
    status: StatusReconciliacao = StatusReconciliacao.CONCILIADO
    divergencias: tuple[str, ...] = ()


def detectar_divergencias(
    registro: ReconciliacaoPDV,
    *,
    vendas_legadas: int = 1,
    efeitos_estoque: int = 1,
    efeitos_cashback_usado: int = 0,
) -> tuple[str, ...]:
    erros: list[str] = []
    if registro.modo == "authoritative_canary":
        if registro.pedido_id and not registro.venda_financeira_id:
            erros.append("pedido_sem_venda")
        if registro.venda_financeira_id and not registro.venda_legada_id:
            erros.append("venda_financeira_sem_venda_legada")
    if vendas_legadas != 1:
        erros.append("dupla_venda" if vendas_legadas > 1 else "venda_ausente")
    estoque_adiado = registro.estoque_estrategia in {
        "canonico_reservado",
        "canonico_reservado_aguardando_producao",
    }
    esperado_estoque = 0 if estoque_adiado else 1
    if efeitos_estoque != esperado_estoque:
        if efeitos_estoque > esperado_estoque:
            erros.append("efeito_estoque_duplicado")
        else:
            erros.append("estoque_ausente")
    if efeitos_cashback_usado > 1:
        erros.append("cashback_duplicado")
    valores = tuple(
        v
        for v in (
            registro.valor_pedido,
            registro.valor_pagamento,
            registro.valor_venda_financeira,
            registro.valor_venda_legada,
        )
        if v is not None
    )
    if valores and any(v != valores[0] for v in valores[1:]):
        erros.append("valor_divergente")
    return tuple(erros)
