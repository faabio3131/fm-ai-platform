"""Regra de apresentação do alerta de validade do catálogo legado."""

from __future__ import annotations

from datetime import date, datetime, timezone


def status_validade_legado(
    *,
    data_validade: date | datetime | None,
    dias_alerta_vencimento: int,
    hoje: date | None = None,
) -> str:
    if data_validade is None:
        return "🟢 No Prazo"

    validade = (
        data_validade.date()
        if isinstance(data_validade, datetime)
        else data_validade
    )
    data_referencia = hoje or datetime.now(timezone.utc).astimezone().date()
    dias_restantes = (validade - data_referencia).days
    if dias_restantes <= 0:
        return "🔴 VENCIDO!"
    if dias_restantes <= dias_alerta_vencimento:
        return f"🟡 Vence em {dias_restantes} dias!"
    return "🟢 No Prazo"
