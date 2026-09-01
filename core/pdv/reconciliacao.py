"""Modelo consultavel e detector conservador de divergencias do checkout."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class StatusReconciliacao(StrEnum):
    CONCILIADO = "conciliado"
    DIVERGENTE = "divergente"
    REPARO_NECESSARIO = "reparo_necessario"


class RecomendacaoCoortePDV(StrEnum):
    """Decisao assistiva do F6-E; nunca altera rollout automaticamente."""

    MANTER = "manter_coorte"
    REDUZIR = "reduzir_coorte"
    AMPLIACAO_ELEGIVEL = "ampliacao_elegivel"


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


@dataclass(frozen=True, kw_only=True)
class RegistroReadinessPDV:
    tenant_id: str
    unidade_id: str
    modo: str
    idempotency_key: str
    status: str
    divergencias: tuple[str, ...]
    criado_em: datetime


@dataclass(frozen=True, kw_only=True)
class MetricaModoTerminalPDV:
    modo: str
    terminal_id: str
    total: int
    conciliados: int
    divergentes: int
    reparo_necessario: int
    pendentes: int

    @property
    def bloqueios(self) -> int:
        return self.divergentes + self.reparo_necessario


@dataclass(frozen=True, kw_only=True)
class ResumoReadinessPDV:
    total_registros: int
    divergentes: int
    reparo_necessario: int
    pendentes: int
    chaves_invalidas: int
    metricas: tuple[MetricaModoTerminalPDV, ...]
    recomendacao: RecomendacaoCoortePDV

    @property
    def apto_ampliacao(self) -> bool:
        return self.recomendacao is RecomendacaoCoortePDV.AMPLIACAO_ELEGIVEL


def extrair_terminal_id_reconciliacao(chave: str) -> str:
    """Extrai terminal da chave pdv:<terminal>:<checkout>:reconciliacao."""

    prefixo = "pdv:"
    sufixo = ":reconciliacao"
    if not chave.startswith(prefixo) or not chave.endswith(sufixo):
        raise ValueError("chave_reconciliacao_pdv_invalida")
    corpo = chave[len(prefixo) : -len(sufixo)]
    terminal, separador, checkout = corpo.partition(":")
    if not separador or not terminal.strip() or not checkout.strip():
        raise ValueError("chave_reconciliacao_pdv_invalida")
    return terminal


def resumir_readiness(
    registros: Iterable[RegistroReadinessPDV],
) -> ResumoReadinessPDV:
    """Produz metricas conservadoras sem mutar reconciliacao nem rollout."""

    materializados = tuple(registros)
    grupos: dict[tuple[str, str], dict[str, int]] = {}
    chaves_invalidas = 0
    divergentes = 0
    reparo_necessario = 0
    pendentes = 0

    for registro in materializados:
        try:
            terminal = extrair_terminal_id_reconciliacao(registro.idempotency_key)
        except ValueError:
            chaves_invalidas += 1
            continue

        chave = (registro.modo, terminal)
        contador = grupos.setdefault(
            chave,
            {
                "total": 0,
                "conciliados": 0,
                "divergentes": 0,
                "reparo_necessario": 0,
                "pendentes": 0,
            },
        )
        contador["total"] += 1
        status = str(registro.status)
        if status == StatusReconciliacao.CONCILIADO.value:
            contador["conciliados"] += 1
        elif status == StatusReconciliacao.DIVERGENTE.value:
            contador["divergentes"] += 1
            divergentes += 1
        elif status == StatusReconciliacao.REPARO_NECESSARIO.value:
            contador["reparo_necessario"] += 1
            reparo_necessario += 1
        else:
            contador["pendentes"] += 1
            pendentes += 1

    metricas = tuple(
        MetricaModoTerminalPDV(
            modo=modo,
            terminal_id=terminal,
            total=contador["total"],
            conciliados=contador["conciliados"],
            divergentes=contador["divergentes"],
            reparo_necessario=contador["reparo_necessario"],
            pendentes=contador["pendentes"],
        )
        for (modo, terminal), contador in sorted(grupos.items())
    )

    if chaves_invalidas or divergentes or reparo_necessario:
        recomendacao = RecomendacaoCoortePDV.REDUZIR
    elif not materializados or pendentes:
        recomendacao = RecomendacaoCoortePDV.MANTER
    else:
        recomendacao = RecomendacaoCoortePDV.AMPLIACAO_ELEGIVEL

    return ResumoReadinessPDV(
        total_registros=len(materializados),
        divergentes=divergentes,
        reparo_necessario=reparo_necessario,
        pendentes=pendentes,
        chaves_invalidas=chaves_invalidas,
        metricas=metricas,
        recomendacao=recomendacao,
    )


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
