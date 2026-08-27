"""Roteamento operacional de itens de Pedido canônico para setores KDS."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

import streamlit as st
from sqlalchemy.orm import Session

from application.kds_roteamento import listar_itens_pendentes
from application.kds_runtime import ServicoKDSCanonico
from application.kds_transacoes import rotear_item_kds_v1
from core.kds.erros import ErroKDS
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

_AUTH_SESSION_KEY = "_fm_ai_authenticated_identity_v1"


def _contexto_runtime() -> ContextoExecucao:
    identidade = st.session_state.get(_AUTH_SESSION_KEY)
    if not isinstance(identidade, IdentidadeUsuario) or not identidade.ativo:
        raise PermissionError("identidade_autenticada_ausente")
    return identidade.contexto(
        origem="kds_roteamento_streamlit",
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
    )


def render_roteamento_kds(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao | None = None,
) -> None:
    contexto_kds = contexto or _contexto_runtime()
    if Permissao.PRODUCAO_ATUALIZAR not in contexto_kds.permissoes:
        return

    with st.expander("📥 Pedidos aguardando roteamento", expanded=False):
        session = session_factory()
        try:
            canonico = ServicoKDSCanonico(session)
            pendentes = listar_itens_pendentes(session, contexto_kds)
            setores = canonico.listar_setores(contexto_kds)
            if not pendentes:
                st.caption("Nenhum item confirmado aguardando setor de produção.")
                return
            if not setores:
                st.warning("Cadastre um setor de produção antes de rotear pedidos.")
                return

            rotulos = {
                f"{item.pedido_id} · {item.nome_produto} · item {item.pedido_item_id}": item
                for item in pendentes
            }
            escolhido = st.selectbox(
                "Item confirmado",
                tuple(rotulos),
                key="kds-roteamento-item",
            )
            item = rotulos[escolhido]
            setores_por_nome = {setor.nome: setor for setor in setores}
            nome_setor = st.selectbox(
                "Setor de destino",
                tuple(setores_por_nome),
                key="kds-roteamento-setor",
            )
            setor = setores_por_nome[nome_setor]
            prioridade = int(
                st.number_input(
                    "Prioridade",
                    min_value=0,
                    max_value=100,
                    value=0,
                    step=1,
                    key="kds-roteamento-prioridade",
                )
            )
            if st.button(
                "Enviar item para produção",
                type="primary",
                key="kds-roteamento-enviar",
            ):
                chave = (
                    f"ui:rotear:{item.pedido_id}:{item.pedido_item_id}:{setor.setor_id}"
                )
                # A sessão desta tela é somente leitura. Libera o snapshot
                # antes de abrir a transação autoritativa da Application.
                session.close()

                resultado = rotear_item_kds_v1(
                    session_factory=session_factory,
                    contexto=contexto_kds,
                    pedido_id=item.pedido_id,
                    pedido_item_id=item.pedido_item_id,
                    setor_id=setor.setor_id,
                    quantidade=item.quantidade,
                    idempotency_key=chave,
                    prioridade=prioridade,
                )
                st.success(
                    "Item enviado ao KDS; "
                    f"pedido={resultado.pedido_status.value}, setor={setor.nome}."
                )
                st.rerun()
        except ErroKDS as exc:
            st.error(f"Roteamento recusado pelo Core: {exc.codigo}")
        finally:
            session.close()
