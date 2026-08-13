"""Renderer comercial do KDS V1 por setor."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import streamlit as st
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from application.kds_runtime import ServicoKDSCanonico
from core.kds.adaptador_sqlalchemy import RepositorioKDSSQLAlchemy
from core.kds.erros import ErroKDS
from core.kds.servicos import CacheFilaKDS, ServicoKDS
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

_AUTH_SESSION_KEY = "_fm_ai_authenticated_identity_v1"


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


def _contexto_runtime() -> ContextoExecucao:
    identidade = st.session_state.get(_AUTH_SESSION_KEY)
    if not isinstance(identidade, IdentidadeUsuario) or not identidade.ativo:
        raise PermissionError("identidade_autenticada_ausente")
    return identidade.contexto(
        origem="kds_streamlit",
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
    )


def _preparar_e2e_se_injetado(engine: Any, contexto: ContextoExecucao | None) -> None:
    if contexto is None:
        return
    if os.getenv("FM_AI_TEST_MODE") != "1":
        raise RuntimeError("contexto_kds_injetado_so_permitido_em_teste")
    from core.kds import preparar_schema_teste

    preparar_schema_teste(engine)


def render_kds(
    *,
    engine: Any,
    session_factory: Callable[[], Session],
    permitir_simulacao_offline: bool = False,
    contexto: ContextoExecucao | None = None,
) -> None:
    """Renderiza KDS comercial ou o mesmo renderer em E2E explicitamente isolado."""

    _preparar_e2e_se_injetado(engine, contexto)
    contexto_kds = contexto or _contexto_runtime()
    modo_e2e = contexto is not None and os.getenv("FM_AI_TEST_MODE") == "1"

    st.header("🍳 KDS por Setor")
    st.caption(
        "Produção operacional por setor — o estado macro do pedido é sincronizado pelo Core."
    )

    sessao: Session | None = None
    try:
        sessao = session_factory()
        canonico = ServicoKDSCanonico(sessao)
        canonico.kds.cache = _cache_sessao()

        offline = False
        if permitir_simulacao_offline and modo_e2e:
            offline = st.checkbox("Simular KDS offline", key="kds-e2e-offline")

        setores = canonico.listar_setores(contexto_kds)
        if not setores:
            st.info("Nenhum setor de produção configurado.")
            return

        opcoes: dict[str, str | None] = {"Todos os setores": None}
        opcoes.update({setor.nome: setor.setor_id for setor in setores})
        nome_setor = st.selectbox("Setor", tuple(opcoes), key="kds-setor")
        setor_id = opcoes[nome_setor]

        if offline:
            servico_offline = ServicoKDS(
                _RepositorioOfflineLeitura(canonico.kds_repo),  # type: ignore[arg-type]
                RepositorioAuditoriaEmMemoria(),
                cache=_cache_sessao(),
            )
            fila = servico_offline.listar_fila_tolerante(
                contexto_kds, setor_id=setor_id
            )
        else:
            fila = canonico.listar_fila(contexto_kds, setor_id=setor_id)

        if fila.degradado:
            st.warning("KDS em modo degradado — somente leitura")
            st.caption(
                "Exibindo o último snapshot conhecido; comandos estão bloqueados."
            )
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
        ) -> None:
            try:
                resultado = canonico.transicionar(
                    contexto_kds,
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
            except Exception:
                sessao.rollback()
                raise
            st.success(
                f"Produção atualizada para {destino}; pedido={resultado.pedido_status.value}."
            )
            st.rerun()

        try:
            if producao.status == "aguardando":
                if st.button("Aceitar", key=f"kds-aceitar-{selecionado}"):
                    executar("aceita", precondicoes={"setor_correto": True})
            elif producao.status == "aceita":
                if st.button("Iniciar", key=f"kds-iniciar-{selecionado}"):
                    executar(
                        "em_preparo",
                        precondicoes={
                            "estoque_resolvido": True,
                            "estacao_apta": True,
                        },
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
            elif (
                producao.status == "pronta"
                and Permissao.EXPEDICAO_OPERAR in contexto_kds.permissoes
                and st.button(
                    "Registrar retirada", key=f"kds-retirar-{selecionado}"
                )
            ):
                executar(
                    "retirada",
                    precondicoes={
                        "conferencia_realizada": True,
                        "posse_transferida": True,
                    },
                )
        except ErroKDS as exc:
            sessao.rollback()
            st.error(f"Comando KDS recusado: {exc.codigo}")
    except PermissionError:
        if sessao is not None:
            sessao.rollback()
        st.error("Seu usuário não possui acesso ao KDS desta unidade.")
    except Exception as exc:  # noqa: BLE001
        if sessao is not None:
            sessao.rollback()
        st.error(f"Não foi possível carregar o KDS: {type(exc).__name__}")
    finally:
        if sessao is not None:
            sessao.close()
