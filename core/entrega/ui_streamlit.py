"""Interface operacional da Expedição e Entrega V1."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import streamlit as st
from sqlalchemy.orm import Session

from application.entrega_transacoes import AplicacaoEntregaV1
from core.seguranca import ContextoExecucao, IdentidadeUsuario, Papel

from .adaptador_sqlalchemy import RepositorioEntregaSQLAlchemy
from .erros import ErroEntrega
from .integracoes_sqlalchemy import (
    financeiro_resolvido_sqlalchemy,
    pedido_cancelado_sqlalchemy,
)
from .modelos import ChecklistExpedicao, ProvaEntrega, StatusEntrega
from .servicos import ServicoEntrega

SessionFactory = Callable[[], Session]
_AUTH_SESSION_KEY = "_fm_ai_authenticated_identity_v1"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _resolver_contexto(contexto: ContextoExecucao | None) -> ContextoExecucao:
    if contexto is not None:
        if os.getenv("FM_AI_TEST_MODE") != "1":
            raise RuntimeError("contexto_injetado_so_permitido_em_teste")
        return contexto

    identidade = st.session_state.get(_AUTH_SESSION_KEY)
    if not isinstance(identidade, IdentidadeUsuario) or not identidade.ativo:
        raise PermissionError("identidade_autenticada_ausente")
    return identidade.contexto(
        origem="entrega_streamlit",
        correlation_id=str(uuid4()),
        solicitado_em=_agora(),
    )


def _servico(session: Session) -> ServicoEntrega:
    return ServicoEntrega(
        RepositorioEntregaSQLAlchemy(session),
        financeiro_resolvido=lambda tenant, unidade, pedido: financeiro_resolvido_sqlalchemy(
            session, tenant, unidade, pedido
        ),
        pedido_cancelado=lambda tenant, unidade, pedido: pedido_cancelado_sqlalchemy(
            session, tenant, unidade, pedido
        ),
    )


def _executar(session: Session, acao: Callable[[], Any]) -> None:
    session.close()
    try:
        acao()
    except ErroEntrega as exc:
        st.error(f"Operação recusada: {exc.codigo}")
        return
    st.rerun()


def render_entrega(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao | None = None,
) -> None:
    """Renderiza o escopo autorizado com identidade real no runtime comercial."""

    contexto = _resolver_contexto(contexto)
    papeis_operacionais = {
        Papel.EXPEDICAO,
        Papel.ENTREGADOR,
        Papel.GERENTE,
        Papel.ADMINISTRADOR,
    }
    if not (contexto.papeis & papeis_operacionais):
        st.error("Papel sem acesso à Expedição e Entrega")
        return

    perfil_expedicao = bool(
        contexto.papeis & {Papel.EXPEDICAO, Papel.GERENTE, Papel.ADMINISTRADOR}
    )
    perfil_entregador = Papel.ENTREGADOR in contexto.papeis
    papeis_ativos = ", ".join(sorted(papel.value for papel in contexto.papeis))

    st.title("Expedição e Entrega")
    st.caption(f"Papel: {papeis_ativos} · usuário: {contexto.usuario_id}")

    with session_factory() as session:
        servico = _servico(session)
        aplicacao = AplicacaoEntregaV1(session_factory)

        try:
            entregas = servico.listar(contexto)
        except ErroEntrega as exc:
            st.error(f"Operação recusada: {exc.codigo}")
            return

        if not entregas:
            st.info("Nenhuma entrega na sua alçada.")
            return

        for entrega in entregas:
            with st.container(border=True):
                st.subheader(f"Pedido {entrega.pedido_id}")
                st.write(f"Status: **{entrega.status.value}**")
                st.write(f"Tentativa: {entrega.tentativa}")
                st.write(f"Entregador: {entrega.entregador_id or 'não atribuído'}")

                if perfil_expedicao:
                    _acoes_expedicao(session, aplicacao, contexto, entrega)
                if perfil_entregador:
                    _acoes_entregador(session, aplicacao, contexto, entrega)


def _acoes_expedicao(
    session: Session,
    aplicacao: AplicacaoEntregaV1,
    contexto: ContextoExecucao,
    entrega: Any,
) -> None:
    if entrega.status is StatusEntrega.AGUARDANDO_EXPEDICAO:
        itens = st.checkbox(
            f"Itens conferidos · {entrega.pedido_id}",
            key=f"entrega-itens-{entrega.entrega_id}",
        )
        embalagem = st.checkbox(
            f"Embalagem conferida · {entrega.pedido_id}",
            key=f"entrega-embalagem-{entrega.entrega_id}",
        )
        identificacao = st.checkbox(
            f"Identificação conferida · {entrega.pedido_id}",
            key=f"entrega-identificacao-{entrega.entrega_id}",
        )
        if st.button(
            f"Concluir checklist · {entrega.pedido_id}",
            key=f"entrega-checklist-{entrega.entrega_id}",
        ):
            _executar(
                session,
                lambda: aplicacao.concluir_checklist(
                    entrega.entrega_id,
                    ChecklistExpedicao(itens, embalagem, identificacao),
                    versao_esperada=entrega.versao,
                    contexto=contexto,
                    idempotency_key=f"ui:checklist:{entrega.entrega_id}:v{entrega.versao}",
                ),
            )

    if entrega.status in {
        StatusEntrega.AGUARDANDO_PRODUCAO,
        StatusEntrega.AGUARDANDO_EXPEDICAO,
        StatusEntrega.AGUARDANDO_ENTREGADOR,
        StatusEntrega.TENTATIVA_FALHOU,
    }:
        if os.getenv("FM_AI_TEST_MODE") == "1":
            entregador_id = st.text_input(
                f"ID do entregador · {entrega.pedido_id}",
                value="",
                key=f"entrega-driver-{entrega.entrega_id}",
            )
            if st.button(
                f"Atribuir entregador · {entrega.pedido_id}",
                key=f"entrega-atribuir-{entrega.entrega_id}",
            ):
                _executar(
                    session,
                    lambda: aplicacao.atribuir(
                        entrega.entrega_id,
                        entregador_id,
                        versao_esperada=entrega.versao,
                        contexto=contexto,
                        idempotency_key=(
                            f"ui:atribuir:{entrega.entrega_id}:v{entrega.versao}"
                        ),
                    ),
                )
        else:
            st.info(
                "Atribuição de entregador está bloqueada até a governança "
                "canônica de usuários ENTREGADOR da F10-D."
            )


def _acoes_entregador(
    session: Session,
    aplicacao: AplicacaoEntregaV1,
    contexto: ContextoExecucao,
    entrega: Any,
) -> None:
    if entrega.status is StatusEntrega.ATRIBUIDA and st.button(
        f"Confirmar coleta · {entrega.pedido_id}",
        key=f"entrega-coletar-{entrega.entrega_id}",
    ):
        _executar(
            session,
            lambda: aplicacao.coletar(
                entrega.entrega_id,
                versao_esperada=entrega.versao,
                contexto=contexto,
                idempotency_key=f"ui:coletar:{entrega.entrega_id}:v{entrega.versao}",
            ),
        )

    if entrega.status is StatusEntrega.COLETADA and st.button(
        f"Sair em rota · {entrega.pedido_id}",
        key=f"entrega-rota-{entrega.entrega_id}",
    ):
        _executar(
            session,
            lambda: aplicacao.sair_em_rota(
                entrega.entrega_id,
                versao_esperada=entrega.versao,
                contexto=contexto,
                idempotency_key=f"ui:rota:{entrega.entrega_id}:v{entrega.versao}",
            ),
        )

    if entrega.status is StatusEntrega.EM_ROTA:
        prova_ref = st.text_input(
            f"Referência da prova · {entrega.pedido_id}",
            value=f"proof://{entrega.pedido_id}",
            key=f"entrega-prova-{entrega.entrega_id}",
        )
        if st.button(
            f"Confirmar entrega · {entrega.pedido_id}",
            key=f"entrega-confirmar-{entrega.entrega_id}",
        ):
            prova = ProvaEntrega(prova_ref, "confirmacao", _agora())
            _executar(
                session,
                lambda: aplicacao.confirmar_entrega(
                    entrega.entrega_id,
                    prova,
                    versao_esperada=entrega.versao,
                    contexto=contexto,
                    idempotency_key=f"ui:entregar:{entrega.entrega_id}:v{entrega.versao}",
                ),
            )

        motivo = st.text_input(
            f"Motivo da tentativa · {entrega.pedido_id}",
            value="cliente ausente",
            key=f"entrega-motivo-{entrega.entrega_id}",
        )
        if st.button(
            f"Registrar tentativa sem sucesso · {entrega.pedido_id}",
            key=f"entrega-falha-{entrega.entrega_id}",
        ):
            _executar(
                session,
                lambda: aplicacao.registrar_tentativa_falha(
                    entrega.entrega_id,
                    motivo,
                    versao_esperada=entrega.versao,
                    contexto=contexto,
                    idempotency_key=f"ui:falha:{entrega.entrega_id}:v{entrega.versao}",
                ),
            )
