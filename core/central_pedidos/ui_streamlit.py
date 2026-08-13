"""UI Streamlit comercial da Central de Pedidos V1.

A tela consulta somente Pedido V1 e executa comandos pela fachada canonica da
Central. O contexto vem da identidade autenticada; contexto artificial existe
apenas quando injetado explicitamente pelo E2E isolado.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import streamlit as st
from sqlalchemy.orm import Session

from core.central_pedidos import CentralPedidosSQLAlchemy, FiltroCentralPedidos
from core.central_pedidos.servicos import ServicoComandosCentral
from core.dominio.erros import ConflitoIdempotencia, PermissaoNegada, RecursoNaoEncontrado
from core.estados.maquinas import ErroTransicao
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao

_AUTH_SESSION_KEY = "_fm_ai_authenticated_identity_v1"


def _contexto_runtime() -> ContextoExecucao:
    identidade = st.session_state.get(_AUTH_SESSION_KEY)
    if not isinstance(identidade, IdentidadeUsuario) or not identidade.ativo:
        raise PermissionError("identidade_autenticada_ausente")
    return identidade.contexto(
        origem="central_pedidos_streamlit",
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
    )


def _preparar_e2e_se_injetado(engine: Any, contexto: ContextoExecucao | None) -> None:
    if contexto is None:
        return
    if os.getenv("FM_AI_TEST_MODE") != "1":
        raise RuntimeError("contexto_injetado_so_permitido_em_teste")
    from core.central_pedidos import preparar_schema_teste

    preparar_schema_teste(engine)


def _executar_transicao(
    *,
    session: Session,
    contexto: ContextoExecucao,
    pedido_id: str,
    destino: str,
    versao: int,
    precondicoes: dict[str, bool] | None = None,
    motivo: str | None = None,
) -> None:
    chave = f"central:{pedido_id}:{versao}:{destino}"
    try:
        ServicoComandosCentral(session).transicionar(
            contexto=contexto,
            pedido_id=pedido_id,
            destino=destino,
            versao_esperada=versao,
            idempotency_key=chave,
            precondicoes=precondicoes,
            motivo=motivo,
            metadata={"origem_ui": "central_pedidos"},
        )
        session.commit()
    except Exception:
        session.rollback()
        raise


def render_central_pedidos(
    *,
    engine: Any,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao | None = None,
) -> None:
    """Renderiza a Central sobre o runtime V1 ou E2E explicitamente injetado."""

    _preparar_e2e_se_injetado(engine, contexto)
    contexto_central = contexto or _contexto_runtime()

    st.header("📋 Central de Pedidos")
    st.caption(
        "Pedidos canônicos em tempo real operacional — mesma fonte usada por PDV, "
        "KDS, salão e integrações."
    )

    col_busca, col_status, col_canal = st.columns(3)
    busca_central = col_busca.text_input(
        "Buscar pedido ou cliente", key="central_busca"
    )
    status_central = col_status.text_input("Status", key="central_status")
    canal_central = col_canal.text_input("Canal", key="central_canal")

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
            st.info("Nenhum pedido encontrado para os filtros atuais.")
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
            f"**Canal:** {detalhe.resumo.canal} · "
            f"**Total:** R$ {detalhe.resumo.total:.2f} · "
            f"**Versão:** {detalhe.resumo.versao}"
        )

        st.markdown("#### Itens")
        for item in detalhe.itens:
            st.write(f"{item.quantidade}× {item.nome} — R$ {item.subtotal:.2f}")
            for adicional in item.adicionais:
                st.caption(f"+ {adicional[1]}× {adicional[0]} — R$ {adicional[3]:.2f}")

        st.markdown("#### Situação financeira")
        st.write(detalhe.financeiro.situacao)
        st.caption(
            "Pagamento: "
            + (", ".join(detalhe.financeiro.pagamento_ids) or "ausente")
        )
        st.caption(
            f"Venda financeira: {detalhe.financeiro.venda_financeira_id or 'ausente'}"
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

        st.markdown("#### Ações operacionais")
        status = detalhe.resumo.status
        versao = detalhe.resumo.versao

        if status == "rascunho":
            if st.button(
                "Enviar para confirmação",
                key=f"central-enviar-{selecionado}-{versao}",
                type="primary",
            ):
                _executar_transicao(
                    session=sessao_central,
                    contexto=contexto_central,
                    pedido_id=selecionado,
                    destino="aguardando_confirmacao",
                    versao=versao,
                    precondicoes={"itens_validos": True, "precos_calculados": True},
                )
                st.success("Pedido enviado para confirmação pelo Core.")
                st.rerun()

        cancelaveis = {
            "rascunho",
            "aguardando_confirmacao",
            "confirmado",
            "enviado_producao",
            "em_preparo",
            "pronto",
            "em_expedicao",
            "saiu_entrega",
        }
        if status in cancelaveis:
            motivo = st.text_input(
                "Motivo do cancelamento",
                key=f"central-motivo-cancelamento-{selecionado}-{versao}",
            )
            if st.button(
                "Cancelar pedido",
                key=f"central-cancelar-{selecionado}-{versao}",
            ):
                if not motivo.strip():
                    st.warning("Informe o motivo do cancelamento.")
                else:
                    _executar_transicao(
                        session=sessao_central,
                        contexto=contexto_central,
                        pedido_id=selecionado,
                        destino="cancelado",
                        versao=versao,
                        motivo=motivo.strip(),
                    )
                    st.success("Pedido cancelado pelo Core com trilha de auditoria.")
                    st.rerun()

        if status in {"concluido", "cancelado"}:
            st.caption("Pedido em estado terminal; não há ações operacionais disponíveis.")

    except ErroTransicao as exc:
        st.warning(f"Ação recusada pelo Core: {exc.codigo}.")
    except (PermissaoNegada, PermissionError):
        st.error("Seu usuário não possui permissão para esta operação.")
    except RecursoNaoEncontrado:
        st.warning("O pedido não está mais disponível nesta unidade.")
    except ConflitoIdempotencia:
        st.warning("A operação já foi processada com conteúdo diferente; atualize a tela.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Não foi possível carregar a Central: {type(exc).__name__}")
    finally:
        if sessao_central is not None:
            sessao_central.close()
