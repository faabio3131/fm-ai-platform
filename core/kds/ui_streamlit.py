"""UI Streamlit reutilizavel do KDS V1.

A superficie executavel desta PR permanece protegida por feature flag de teste.
Regras, RBAC, idempotencia e optimistic locking ficam no ServicoKDS.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import streamlit as st
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core.kds import (
    CacheFilaKDS,
    ErroKDS,
    RepositorioAuditoriaEmMemoria,
    RepositorioKDSSQLAlchemy,
    ServicoKDS,
    contexto_kds_teste,
    preparar_schema_teste,
)


class _RepositorioOfflineLeitura:
    """Proxy exclusivo de E2E que derruba apenas a leitura da fila."""

    def __init__(self, base: RepositorioKDSSQLAlchemy) -> None:
        self._base = base

    def listar_fila(self, *args: Any, **kwargs: Any):
        del args, kwargs
        raise OperationalError("kds_e2e_offline", {}, Exception("offline"))

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._base, nome)


def _cache_sessao() -> CacheFilaKDS:
    chave = "_fm_ai_kds_cache_v1"
    if chave not in st.session_state:
        st.session_state[chave] = CacheFilaKDS()
    return st.session_state[chave]


def render_kds(
    *,
    engine: Any,
    session_factory: Callable[[], Session],
    permitir_simulacao_offline: bool = False,
) -> None:
    """Renderiza fila KDS real sobre backend V1 em contexto E2E protegido."""
    preparar_schema_teste(engine)
    st.header("🍳 KDS por Setor")
    st.caption("Fila operacional de Produção V1 — Pedido continua autoritativo.")

    sessao: Session | None = None
    try:
        sessao = session_factory()
        repositorio_base = RepositorioKDSSQLAlchemy(sessao)
        offline = False
        if permitir_simulacao_offline:
            offline = st.checkbox("Simular KDS offline", key="kds-e2e-offline")
        repositorio = (
            _RepositorioOfflineLeitura(repositorio_base) if offline else repositorio_base
        )
        auditoria = RepositorioAuditoriaEmMemoria()
        servico = ServicoKDS(
            repositorio,  # type: ignore[arg-type]
            auditoria,
            cache=_cache_sessao(),
        )
        contexto_cozinha = contexto_kds_teste(
            correlation_id=str(uuid4()),
            solicitado_em=datetime.now(timezone.utc),
            papel="cozinha",
        )
        setores = servico.listar_setores(contexto_cozinha)
        if not setores:
            st.info("Nenhum setor de produção configurado.")
            return

        opcoes: dict[str, str | None] = {"Todos os setores": None}
        opcoes.update({setor.nome: setor.setor_id for setor in setores})
        nome_setor = st.selectbox("Setor", tuple(opcoes), key="kds-setor")
        setor_id = opcoes[nome_setor]
        fila = servico.listar_fila_tolerante(contexto_cozinha, setor_id=setor_id)

        if fila.degradado:
            st.warning("KDS em modo degradado — somente leitura")
            st.caption("Exibindo o último snapshot conhecido; comandos estão bloqueados.")
        else:
            st.caption(f"Fila atualizada em {fila.atualizado_em.isoformat()}")

        if not fila.itens:
            st.info("Fila vazia para o filtro selecionado.")
            return

        st.dataframe(
            [
                {
                    "Produção": item.producao.producao_id,
                    "Pedido": item.producao.pedido_id,
                    "Setor": item.setor.nome,
                    "Status": item.producao.status,
                    "Prioridade": item.producao.prioridade,
                    "SLA": item.sla.estado.value,
                    "Restante (s)": item.sla.restante_segundos,
                }
                for item in fila.itens
            ],
            width="stretch",
            hide_index=True,
        )

        ids = [item.producao.producao_id for item in fila.itens]
        selecionado = st.selectbox("Abrir produção", ids, key="kds-producao")
        item_fila = next(
            item for item in fila.itens if item.producao.producao_id == selecionado
        )
        producao = item_fila.producao
        st.subheader(f"Produção {producao.producao_id}")
        st.write(f"**Pedido:** {producao.pedido_id}")
        st.write(f"**Setor:** {item_fila.setor.nome}")
        st.write(f"**Status:** {producao.status}")
        st.write(f"**Versão:** {producao.versao}")
        st.write(f"**SLA:** {item_fila.sla.estado.value}")

        if fila.somente_leitura:
            return

        def executar(
            destino: str,
            *,
            precondicoes: dict[str, bool] | None = None,
            motivo: str | None = None,
            papel: str = "cozinha",
        ) -> None:
            contexto = contexto_kds_teste(
                correlation_id=str(uuid4()),
                solicitado_em=datetime.now(timezone.utc),
                papel=papel,
            )
            servico.transicionar(
                contexto,
                producao_id=producao.producao_id,
                destino=destino,
                versao_esperada=producao.versao,
                idempotency_key=(
                    f"ui:{producao.producao_id}:{producao.versao}:{destino}"
                ),
                precondicoes=precondicoes,
                motivo=motivo,
            )
            sessao.commit()
            st.success(f"Produção atualizada para {destino}.")
            st.rerun()

        try:
            if producao.status == "aguardando":
                if st.button("Aceitar", key=f"kds-aceitar-{selecionado}"):
                    executar("aceita", precondicoes={"setor_correto": True})
            elif producao.status == "aceita":
                if st.button("Iniciar", key=f"kds-iniciar-{selecionado}"):
                    executar(
                        "em_preparo",
                        precondicoes={"estoque_resolvido": True, "estacao_apta": True},
                    )
            elif producao.status == "em_preparo":
                motivo = st.text_input(
                    "Motivo da pausa", key=f"kds-motivo-{selecionado}"
                )
                col_pausa, col_pronto = st.columns(2)
                if col_pausa.button("Pausar", key=f"kds-pausar-{selecionado}"):
                    executar("pausada", motivo=motivo)
                if col_pronto.button("Marcar pronto", key=f"kds-pronto-{selecionado}"):
                    executar(
                        "pronta",
                        precondicoes={
                            "quantidade_concluida": True,
                            "checklist_concluido": True,
                        },
                    )
            elif producao.status == "pausada":
                if st.button("Retomar", key=f"kds-retomar-{selecionado}"):
                    executar(
                        "em_preparo",
                        precondicoes={"impedimento_resolvido": True},
                    )
            elif producao.status == "pronta" and st.button(
                "Registrar retirada", key=f"kds-retirar-{selecionado}"
            ):
                executar(
                    "retirada",
                    precondicoes={
                        "conferencia_realizada": True,
                        "posse_transferida": True,
                    },
                    papel="expedicao",
                )
        except ErroKDS as exc:
            sessao.rollback()
            st.error(f"Comando KDS recusado: {exc.codigo}")
    except Exception as exc:  # noqa: BLE001
        if sessao is not None:
            sessao.rollback()
        st.error(f"Não foi possível carregar o KDS: {type(exc).__name__}")
    finally:
        if sessao is not None:
            sessao.close()
