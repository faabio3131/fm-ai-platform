"""UI comercial de observabilidade e reimpressão do spool V1."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st
from sqlalchemy.orm import Session

from application.impressao_transacoes import AplicacaoImpressaoV1
from core.impressao import StatusImpressao
from core.seguranca.autenticacao import IdentidadeUsuario
from infra.impressao import ImpressoraTCPRaw, ResolverDestinosImpressaoSQLAlchemy


def render_impressao_operacional(
    *,
    identidade: IdentidadeUsuario,
    session_factory: Callable[[], Session],
) -> None:
    contexto = identidade.contexto(origem="streamlit.impressao_operacional")
    with session_factory() as session:
        destinos = ResolverDestinosImpressaoSQLAlchemy(session).listar(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
    app = AplicacaoImpressaoV1(
        session_factory,
        impressora=ImpressoraTCPRaw(),
        destinos=destinos,
    )
    jobs = app.listar(contexto=contexto)

    st.header("🖨️ Impressão Operacional")
    st.caption(
        "Spool auxiliar do KDS. Falha de impressora não altera Pedido nem Produção."
    )
    if not destinos:
        st.warning("Nenhum destino de impressão ativo configurado para esta unidade.")
    if not jobs:
        st.info("Nenhum job de impressão encontrado nesta unidade.")
        return

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Criado": job.criado_em,
                    "Setor": job.setor_id,
                    "Pedido": job.pedido_id,
                    "Status": job.status.value,
                    "Tentativa": f"{job.tentativa}/{job.max_tentativas}",
                    "Impressora": job.impressora_id,
                }
                for job in reversed(jobs)
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )

    job_id = st.selectbox(
        "Selecionar job",
        options=[job.job_id for job in reversed(jobs)],
        format_func=lambda jid: next(
            f"{j.pedido_id} · {j.setor_id} · {j.status.value}" for j in jobs if j.job_id == jid
        ),
        key="f9d_print_job",
    )
    selecionado = next(job for job in jobs if job.job_id == job_id)
    st.code(selecionado.conteudo, language=None)

    c1, c2 = st.columns(2)
    with c1:
        if selecionado.status in {StatusImpressao.PENDENTE, StatusImpressao.FALHOU}:
            if st.button("Processar impressão", type="primary", use_container_width=True):
                try:
                    resultado = app.processar(contexto=contexto, job_id=job_id)
                    if resultado.impresso:
                        st.success("Impressão enviada com sucesso.")
                    elif resultado.contingencia:
                        st.warning("Job movido para contingência.")
                    else:
                        st.error("Impressora indisponível; tentativa registrada.")
                    st.rerun()
                except Exception:
                    st.error("Não foi possível processar o job de impressão.")
    with c2:
        motivo = st.text_input(
            "Motivo da reimpressão",
            placeholder="Ex.: ticket danificado",
            key="f9d_reprint_reason",
        )
        if st.button("Criar reimpressão", use_container_width=True):
            try:
                app.reimprimir(
                    contexto=contexto,
                    job_id=job_id,
                    motivo=motivo,
                    idempotency_key=f"ui-reprint:{job_id}:{uuid4()}",
                )
                st.success("Reimpressão criada no spool.")
                st.rerun()
            except Exception:
                st.error("Reimpressão não autorizada ou motivo inválido.")
