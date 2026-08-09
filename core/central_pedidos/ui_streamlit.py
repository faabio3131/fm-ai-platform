"""UI Streamlit reutilizável da Central de Pedidos V1.

A composição recebe engine e fábrica de sessão por injeção. Regras de domínio,
RBAC e transições continuam nos serviços existentes da Central.
"""

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import streamlit as st
from sqlalchemy.orm import Session

from core.central_pedidos import (
    CentralPedidosSQLAlchemy,
    FiltroCentralPedidos,
    RepositorioAuditoriaEmMemoria,
    contexto_central_teste,
    preparar_schema_teste,
)
from core.central_pedidos.servicos import ServicoComandosCentral
from core.estados.maquinas import ErroTransicao


def render_central_pedidos(
    *,
    engine: Any,
    session_factory: Callable[[], Session],
) -> None:
    """Renderiza a Central usando somente o backend V1 e contexto E2E protegido."""
    preparar_schema_teste(engine)
    st.header("📋 Central de Pedidos")
    st.caption("Projeção operacional de Pedidos V1 — atualização automática desativada.")

    col_busca, col_status, col_canal = st.columns(3)
    busca_central = col_busca.text_input(
        "Buscar pedido ou cliente", key="central_busca"
    )
    status_central = col_status.text_input("Status", key="central_status")
    canal_central = col_canal.text_input("Canal", key="central_canal")

    contexto_central = contexto_central_teste(
        correlation_id=str(uuid4()), solicitado_em=datetime.now(timezone.utc)
    )

    sessao_central: Session | None = None
    try:
        sessao_central = session_factory()
        central = CentralPedidosSQLAlchemy(sessao_central)
        pagina_central = central.listar(
            contexto_central,
            FiltroCentralPedidos(
                busca=busca_central or None,
                status=(status_central,) if status_central else (),
                canal=(canal_central,) if canal_central else (),
            ),
        )

        if not pagina_central.itens:
            st.info("Nenhum pedido encontrado.")
            return

        st.dataframe(
            [
                {
                    "Pedido": item.pedido_id,
                    "Status": item.status,
                    "Canal": item.canal,
                    "Horário (UTC)": item.criado_em.isoformat(),
                    "Total": f"R$ {item.total:.2f}",
                    "Financeiro": item.financeiro.situacao,
                    "Alerta": "Sim" if item.possui_alerta else "Não",
                }
                for item in pagina_central.itens
            ],
            width="stretch",
            hide_index=True,
        )

        selecionado = st.selectbox(
            "Abrir detalhe", [item.pedido_id for item in pagina_central.itens]
        )
        detalhe = central.detalhar(contexto_central, selecionado)
        if not detalhe:
            return

        st.subheader(f"Pedido {selecionado}")
        st.write(
            f"**Status:** {detalhe.resumo.status} · "
            f"**Total:** R$ {detalhe.resumo.total:.2f} · "
            f"**Versão:** {detalhe.resumo.versao}"
        )

        st.markdown("#### Itens")
        for item in detalhe.itens:
            st.write(f"{item.quantidade}× {item.nome} — R$ {item.subtotal:.2f}")
            for adicional in item.adicionais:
                st.caption(
                    f"+ {adicional[1]}× {adicional[0]} — R$ {adicional[3]:.2f}"
                )

        st.markdown("#### Situação financeira")
        st.write(detalhe.financeiro.situacao)
        st.caption(
            "Pagamento: "
            + (", ".join(detalhe.financeiro.pagamento_ids) or "ausente")
        )
        st.caption(
            f"VendaFinanceira: {detalhe.financeiro.venda_financeira_id or 'ausente'}"
        )
        st.caption(
            f"Venda legada vinculada: {detalhe.financeiro.venda_legada_id or 'ausente'}"
        )
        st.caption(
            f"Reconciliação: {detalhe.financeiro.reconciliacao_id or 'ausente'}"
        )

        st.markdown("#### Alertas")
        if detalhe.alertas:
            for alerta in detalhe.alertas:
                st.warning(f"{alerta.tipo}: {alerta.mensagem}")
        else:
            st.caption("Sem alertas operacionais.")

        st.markdown("#### Timeline")
        for evento in detalhe.timeline:
            st.write(f"{evento.ocorrido_em.isoformat()} — {evento.tipo}")

        st.markdown("#### Ações de teste RBAC")
        st.caption(
            "Disponíveis somente no modo E2E isolado; produção exige identidade humana confiável."
        )

        if detalhe.resumo.status == "rascunho" and st.button(
            "Enviar para confirmação", key=f"central-acao-{selecionado}"
        ):
            auditoria = RepositorioAuditoriaEmMemoria()
            ServicoComandosCentral(sessao_central, auditoria).transicionar(
                contexto=contexto_central,
                pedido_id=selecionado,
                destino="aguardando_confirmacao",
                versao_esperada=detalhe.resumo.versao,
                idempotency_key=f"ui:{selecionado}:aguardando",
                precondicoes={
                    "itens_validos": True,
                    "precos_calculados": True,
                },
            )
            sessao_central.commit()
            st.success(
                f"Comando permitido; evento e auditoria registrados ({len(auditoria.eventos)})."
            )

        if st.button("Demonstrar ação negada", key=f"central-negada-{selecionado}"):
            auditoria = RepositorioAuditoriaEmMemoria()
            contexto_negado = contexto_central_teste(
                correlation_id=str(uuid4()),
                solicitado_em=datetime.now(timezone.utc),
                papel="atendimento",
            )
            try:
                ServicoComandosCentral(sessao_central, auditoria).transicionar(
                    contexto=contexto_negado,
                    pedido_id=selecionado,
                    destino="aguardando_confirmacao",
                    versao_esperada=detalhe.resumo.versao,
                    idempotency_key=f"ui:{selecionado}:negado",
                    precondicoes={
                        "itens_validos": True,
                        "precos_calculados": True,
                    },
                )
            except ErroTransicao as erro:
                st.warning(
                    f"Comando negado por RBAC: {erro.codigo}; "
                    f"auditoria={len(auditoria.eventos)}."
                )

        if st.button(
            "Demonstrar versão desatualizada",
            key=f"central-concorrente-{selecionado}",
        ):
            auditoria = RepositorioAuditoriaEmMemoria()
            try:
                ServicoComandosCentral(sessao_central, auditoria).transicionar(
                    contexto=contexto_central,
                    pedido_id=selecionado,
                    destino="aguardando_confirmacao",
                    versao_esperada=0,
                    idempotency_key=f"ui:{selecionado}:concorrente",
                    precondicoes={
                        "itens_validos": True,
                        "precos_calculados": True,
                    },
                )
            except ErroTransicao as erro:
                st.warning(f"Optimistic locking: {erro.codigo}.")
    except Exception as exc:
        st.error(f"Não foi possível carregar a Central: {type(exc).__name__}")
    finally:
        if sessao_central is not None:
            sessao_central.close()
