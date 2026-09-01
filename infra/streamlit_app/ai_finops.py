"""Dashboard Streamlit read-only sobre o AI FinOps Read Model."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from application.ai_finops_dashboard import resumir_ai_finops
from core.ai_finops import PortaAIFinOpsReadModel


def _percent(valor: Decimal) -> str:
    return f"{valor:.1f}%"


def _decimal(valor: Decimal) -> str:
    return f"{valor:.6f}"


def render_ai_finops_dashboard(
    *,
    read_model: PortaAIFinOpsReadModel,
    tenant_id: str,
    unidade_id: str,
    hoje: date | None = None,
) -> None:
    """Renderiza somente dados já agregados; nunca executa o projector."""

    referencia = hoje or datetime.now(timezone.utc).date()
    inicio_padrao = referencia - timedelta(days=29)

    st.header("💡 AI FinOps — Uso, Custo & Eficiência")
    st.caption(
        "Painel somente leitura sobre agregados AI FinOps da unidade ativa. "
        "Abrir esta tela não varre eventos brutos e não realiza chamadas de IA."
    )

    col_inicio, col_fim = st.columns(2)
    with col_inicio:
        inicio = st.date_input(
            "Período inicial",
            value=inicio_padrao,
            key="ai_finops_inicio",
        )
    with col_fim:
        fim = st.date_input(
            "Período final",
            value=referencia,
            key="ai_finops_fim",
        )

    if not isinstance(inicio, date) or not isinstance(fim, date):
        st.warning("Selecione datas válidas para o período do AI FinOps.")
        return
    if fim < inicio:
        st.warning("O período final não pode ser anterior ao período inicial.")
        return

    try:
        buckets = read_model.listar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            inicio=inicio,
            fim=fim,
        )
    except SQLAlchemyError:
        st.info(
            "AI FinOps ainda não está disponível neste banco. "
            "Aplique a migration canônica antes de consultar o painel."
        )
        return

    if not buckets:
        st.info(
            "Ainda não existem agregados AI FinOps para este período e unidade. "
            "O painel não processa usage bruto durante a abertura."
        )
        return

    resumo = resumir_ai_finops(buckets)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tentativas de IA", f"{resumo.attempts:,}")
    m2.metric("Taxa de sucesso", _percent(resumo.success_rate_pct))
    m3.metric("Taxa de fallback", _percent(resumo.fallback_rate_pct))
    m4.metric("Latência média", f"{resumo.latency_ms_average:.1f} ms")

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Tokens de entrada", f"{resumo.input_tokens:,}")
    t2.metric("Tokens de saída", f"{resumo.output_tokens:,}")
    t3.metric("Tokens em cache", f"{resumo.cached_tokens:,}")
    t4.metric("Cobertura de custo", _percent(resumo.cost_coverage_pct))

    st.markdown("---")
    st.subheader("💰 Custo conhecido por moeda")

    if resumo.custos:
        st.dataframe(
            [
                {
                    "Moeda": custo.moeda,
                    "Custo conhecido": _decimal(custo.valor),
                    "Eventos com custo": custo.eventos,
                }
                for custo in resumo.custos
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning(
            "Nenhum evento do período possui custo conhecido. "
            "O painel não estima nem inventa valores ausentes."
        )

    if resumo.cost_unknown_events:
        st.warning(
            f"{resumo.cost_unknown_events} tentativa(s) ainda estão sem custo "
            "conhecido e permanecem separadas do total financeiro."
        )

    st.info(
        "Economia monetária não é calculada sem um baseline comparável e "
        "aprovado. Tokens em cache são exibidos como eficiência técnica, "
        "não como economia financeira presumida."
    )

    st.markdown("---")
    st.subheader("🧭 Mix de provider e modelo")
    st.dataframe(
        [
            {
                "Provider": item.provider,
                "Modelo": item.model,
                "Tentativas": item.attempts,
            }
            for item in resumo.mix
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        f"Falhas: {resumo.failure_attempts:,} · "
        f"Fallbacks: {resumo.fallback_attempts:,} · "
        f"Latência máxima: {resumo.latency_ms_max:,} ms"
    )
