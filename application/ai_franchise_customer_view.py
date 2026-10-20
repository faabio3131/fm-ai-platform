"""Leitura comercial segura do consumo de IA para o proprietário.

NÃO retorna preços internos de provedores, dólares, limites monetários, IDs de
reservas ou prompts. O ledger transacional (não a projeção diária) é a autoridade.
Não cria nem altera franquias e não consulta Command ou modelos externos.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from infra.ai_budget_sqlalchemy import FranquiaAIBudgetORM


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _porcentagem(*, total: Decimal, usado: Decimal) -> str:
    if total <= 0:
        return "100.0"
    percent = (max(Decimal(0), usado) * Decimal(100) / total).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP,
    )
    return str(min(Decimal("100.0"), percent).quantize(Decimal("0.1")))


def _estado(percent: Decimal) -> str:
    if percent >= 100:
        return "blocked"
    if percent >= 90:
        return "critical"
    if percent >= 70:
        return "warning"
    return "normal"


def consultar_franquias_ia(
    session_factory: Callable[[], Session],
    *,
    tenant_id: str,
    unidade_id: str,
    agora: datetime | None = None,
) -> dict[str, object]:
    """Consulta apenas a unidade da sessão, com alerta em 70/90/100%.

    A unidade não pode receber dados de outro tenant. O custo em USD/BRL é
    mantido exclusivamente no backend e nas telas internas da FM Tecnologia.
    """
    if not tenant_id or not unidade_id:
        raise ValueError("ai_franchise.escopo_obrigatorio")

    instant = _utc(agora or datetime.now(timezone.utc))
    with session_factory() as session:
        rows = tuple(session.scalars(
            select(FranquiaAIBudgetORM).where(
                FranquiaAIBudgetORM.tenant_id == tenant_id,
                FranquiaAIBudgetORM.unidade_id == unidade_id,
            ).order_by(
                FranquiaAIBudgetORM.capability,
                FranquiaAIBudgetORM.vigencia_fim,
            )
        ).all())

    items: list[dict[str, object]] = []
    for row in rows:
        if not (_utc(row.vigencia_inicio) <= instant < _utc(row.vigencia_fim)):
            continue
        percentual = _porcentagem(
            total=row.limite,
            usado=row.consumido + row.reservado,
        )
        state = _estado(Decimal(percentual))
        items.append({
            "capability": row.capability,
            "ciclo_id": row.ciclo_id,
            "fim_ciclo": _utc(row.vigencia_fim).isoformat(),
            "percentual_utilizado": percentual,
            "estado": state,
            "em_processamento": row.reservado > 0,
        })

    if not items:
        return {
            "status": "not_configured",
            "percentual_utilizado": None,
            "franquias": [],
            "mensagem": "A franquia de IA ainda não está configurada para esta unidade.",
        }
    worst = max(Decimal(str(row["percentual_utilizado"])) for row in items)
    state = _estado(worst)
    messages = {
        "normal": "O consumo da sua franquia de IA está dentro do limite.",
        "warning": "Sua franquia de IA atingiu 70% ou mais neste ciclo.",
        "critical": "Atenção: sua franquia de IA atingiu 90% ou mais.",
        "blocked": "O limite de IA foi atingido. As demais operações do restaurante continuam disponíveis.",
    }
    return {
        "status": state,
        "percentual_utilizado": str(worst),
        "franquias": items,
        "mensagem": messages[state],
    }
