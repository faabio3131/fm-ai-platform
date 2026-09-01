"""Interface operacional mínima da Expedição e Entrega V1."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from sqlalchemy.orm import Session

from application.entrega_transacoes import AplicacaoEntregaV1
from core.seguranca import Papel

from .adaptador_sqlalchemy import RepositorioEntregaSQLAlchemy
from .erros import ErroEntrega
from .integracoes_sqlalchemy import (
    financeiro_resolvido_sqlalchemy,
    pedido_cancelado_sqlalchemy,
)
from .modelos import ChecklistExpedicao, ProvaEntrega, StatusEntrega
from .runtime_teste import contexto_entrega_teste
from .servicos import ServicoEntrega

SessionFactory = Callable[[], Session]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _contexto(papel: str, usuario_id: str):
    return contexto_entrega_teste(
        correlation_id=f"entrega-ui-{papel}-{usuario_id}",
        solicitado_em=_agora(),
        papel=papel,
        usuario_id=usuario_id,
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
    # A Session desta tela é somente leitura. Ela é fechada antes do
    # write autoritativo para evitar concorrência com a nova UoW.
    session.close()

    try:
        acao()
    except ErroEntrega as exc:
        st.error(f"Operação recusada: {exc.codigo}")
        return

    st.rerun()


def render_entrega(*, session_factory: SessionFactory, papel: str, usuario_id: str) -> None:
    """Renderiza somente o escopo autorizado para expedição/entregador."""
    if papel not in {Papel.EXPEDICAO.value, Papel.ENTREGADOR.value, Papel.GERENTE.value}:
        st.error("Papel sem acesso à Expedição e Entrega")
        return

    contexto = _contexto(papel, usuario_id)
    st.title("Expedição e Entrega")
    st.caption(f"Papel: {papel} · usuário: {usuario_id}")

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

                if papel in {Papel.EXPEDICAO.value, Papel.GERENTE.value}:
                    _acoes_expedicao(session, aplicacao, contexto, entrega)
                if papel == Papel.ENTREGADOR.value:
                    _acoes_entregador(session, aplicacao, contexto, entrega)


def _acoes_expedicao(
    session: Session,
    aplicacao: AplicacaoEntregaV1,
    contexto: Any,
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
        entregador_id = st.text_input(
            f"ID do entregador · {entrega.pedido_id}",
            value="driver-1",
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
                    idempotency_key=f"ui:atribuir:{entrega.entrega_id}:v{entrega.versao}",
                ),
            )


def _acoes_entregador(
    session: Session,
    aplicacao: AplicacaoEntregaV1,
    contexto: Any,
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
