"""UI Streamlit responsiva da interface do garçom V1."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from typing import Any
from uuid import uuid4

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.garcom_transacoes import AplicacaoGarcomV1
from core.kds import RepositorioKDSSQLAlchemy
from core.pedidos.modelos_orm import PedidoORM
from core.salao import ErroSalao, RepositorioSalaoSQLAlchemy, StatusComanda
from core.salao.modelos_orm import PedidoComandaORM
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel

from .erros import ErroGarcom
from .servicos import ServicoGarcom

_AUTH_SESSION_KEY = "_fm_ai_authenticated_identity_v1"

_CSS = """
<style>
.fm-garcom-meta {
  font-size: 0.92rem;
  opacity: 0.82;
}
.fm-garcom-ready {
  border: 2px solid currentColor;
  border-radius: 0.75rem;
  padding: 0.75rem 0.9rem;
  margin: 0.4rem 0;
  font-weight: 600;
}
div[data-testid="stButton"] > button {
  min-height: 44px;
  width: 100%;
}
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"] > div {
  min-height: 44px;
}
@media (max-width: 600px) {
  .block-container {
    padding-top: 1rem;
    padding-left: 0.75rem;
    padding-right: 0.75rem;
  }
  h1, h2, h3 {
    line-height: 1.18;
  }
}
</style>
"""


def _rotulo_mesa(codigo: str | None) -> str:
    return f"Mesa {codigo}" if codigo else "Sem mesa"


def _executar_write(
    sessao: Session,
    acao: Callable[[], Any],
) -> None:
    # A Session do painel pertence somente às leituras. Fechamos antes
    # de abrir a UoW autoritativa para evitar concorrência/lock SQLite.
    sessao.close()
    acao()
    st.rerun()


def _resolver_contexto(contexto: ContextoExecucao | None) -> ContextoExecucao:
    if contexto is not None:
        if os.getenv("FM_AI_TEST_MODE") != "1":
            raise RuntimeError("contexto_injetado_so_permitido_em_teste")
        return contexto

    identidade = st.session_state.get(_AUTH_SESSION_KEY)
    if not isinstance(identidade, IdentidadeUsuario) or not identidade.ativo:
        raise PermissionError("identidade_autenticada_ausente")
    return identidade.contexto(
        origem="garcom_streamlit",
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
    )


def render_garcom(
    *,
    engine: Any,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao | None = None,
) -> None:
    """Renderiza a jornada móvel com identidade real ou E2E explicitamente isolado."""

    _ = engine
    contexto = _resolver_contexto(contexto)
    perfil_garcom = (
        Papel.GARCOM in contexto.papeis
        and not ({Papel.ADMINISTRADOR, Papel.GERENTE} & contexto.papeis)
    )
    papeis_ativos = ", ".join(sorted(p.value for p in contexto.papeis))

    st.markdown(_CSS, unsafe_allow_html=True)
    st.header("Atendimento do Garçom")
    st.caption(
        "Celular/tablet · atualização automática a cada 3 segundos · "
        "Pedido, KDS e Salão permanecem autoritativos."
    )
    st.markdown(
        f'<div class="fm-garcom-meta">Perfil ativo: <strong>{papeis_ativos}</strong></div>',
        unsafe_allow_html=True,
    )

    @st.fragment(run_every="3s")
    def _painel() -> None:
        sessao: Session | None = None
        try:
            sessao = session_factory()
            repositorio_salao = RepositorioSalaoSQLAlchemy(sessao)
            servico = ServicoGarcom(
                repositorio_salao,
                RepositorioKDSSQLAlchemy(sessao),
                agora=lambda: datetime.now(timezone.utc),
            )
            aplicacao = AplicacaoGarcomV1(session_factory)
            painel = servico.listar_painel(contexto)
            st.caption(
                "Atualizado em "
                + painel.atualizado_em.astimezone(timezone.utc).strftime("%H:%M:%S UTC")
            )

            if painel.kds_degradado:
                st.warning(
                    "Avisos da cozinha temporariamente indisponíveis. "
                    "A interface continua somente com a leitura do salão."
                )

            st.subheader("Pedidos prontos")
            if painel.alertas_prontos:
                for alerta in painel.alertas_prontos:
                    st.markdown(
                        '<div class="fm-garcom-ready" role="status">'
                        f'Pedido {alerta.pedido_id} pronto · {_rotulo_mesa(alerta.mesa_codigo)} '
                        f'· Comanda {alerta.comanda_numero} · {alerta.setor_nome}'
                        "</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Nenhum pedido pronto para suas comandas neste momento.")

            st.subheader("Mesas e comandas")
            mesas_por_id = {mesa.mesa_id: mesa for mesa in painel.mesas}
            comandas_por_mesa: dict[str, list] = {}
            for comanda in painel.comandas:
                if comanda.mesa_id:
                    comandas_por_mesa.setdefault(comanda.mesa_id, []).append(comanda)

            for mesa in painel.mesas:
                ativas = comandas_por_mesa.get(mesa.mesa_id, [])
                titulo = f"Mesa {mesa.codigo} · {mesa.status}"
                with st.expander(titulo, expanded=bool(ativas)):
                    st.write(f"Capacidade: {mesa.capacidade}")
                    if not ativas:
                        if mesa.disponivel_para_abertura and st.button(
                            f"Abrir comanda na Mesa {mesa.codigo}",
                            key=f"garcom-abrir-{mesa.mesa_id}",
                        ):
                            _executar_write(
                                sessao,
                                partial(
                                    aplicacao.abrir_comanda,
                                    contexto,
                                    mesa_id=mesa.mesa_id,
                                    expected_mesa_version=mesa.versao,
                                ),
                            )
                        continue

                    for comanda in ativas:
                        st.markdown(f"### Comanda {comanda.numero}")
                        st.write(f"Status: {comanda.status}")
                        st.write(f"Total: R$ {comanda.total:.2f}")
                        st.write(f"Saldo: R$ {comanda.saldo:.2f}")
                        if comanda.propria:
                            st.caption("Comanda sob sua responsabilidade.")
                        else:
                            st.caption("Comanda visível por alçada gerencial.")

                        participantes = repositorio_salao.listar_participantes(
                            contexto.tenant_id,
                            contexto.unidade_id,
                            comanda.comanda_id,
                        )
                        if participantes:
                            st.write(
                                "Participantes: "
                                + ", ".join(
                                    p.apelido or p.participante_id for p in participantes
                                )
                            )

                        pedidos = repositorio_salao.listar_pedidos(
                            contexto.tenant_id,
                            contexto.unidade_id,
                            comanda.comanda_id,
                        )
                        if pedidos:
                            st.write(
                                "Pedidos: "
                                + ", ".join(item.pedido_id for item in pedidos)
                            )

                        if comanda.status in {
                            StatusComanda.ABERTA.value,
                            StatusComanda.EM_CONSUMO.value,
                        }:
                            apelido = st.text_input(
                                "Nome do participante",
                                key=f"garcom-participante-{comanda.comanda_id}",
                                placeholder="Ex.: Ana",
                            )
                            if st.button(
                                "Adicionar participante",
                                key=f"garcom-participante-add-{comanda.comanda_id}",
                            ):
                                if not apelido.strip():
                                    raise ErroGarcom("participante_sem_apelido")
                                _executar_write(
                                    sessao,
                                    partial(
                                        aplicacao.adicionar_participante,
                                        contexto,
                                        comanda_id=comanda.comanda_id,
                                        apelido=apelido,
                                        expected_version=comanda.versao,
                                    ),
                                )

                            vinculados = select(PedidoComandaORM.pedido_id).where(
                                PedidoComandaORM.tenant_id == contexto.tenant_id,
                                PedidoComandaORM.unidade_id == contexto.unidade_id,
                            )
                            consulta = (
                                select(PedidoORM)
                                .where(
                                    PedidoORM.tenant_id == contexto.tenant_id,
                                    PedidoORM.unidade_id == contexto.unidade_id,
                                    PedidoORM.status != "cancelado",
                                    PedidoORM.id.notin_(vinculados),
                                )
                                .order_by(PedidoORM.criado_em, PedidoORM.id)
                            )
                            disponiveis = tuple(sessao.scalars(consulta))
                            if disponiveis:
                                opcoes = {
                                    f"{pedido.id} · R$ {pedido.total:.2f}": pedido
                                    for pedido in disponiveis
                                }
                                selecionado = st.selectbox(
                                    "Pedido disponível",
                                    tuple(opcoes),
                                    key=f"garcom-pedido-{comanda.comanda_id}",
                                )
                                if st.button(
                                    "Vincular pedido à comanda",
                                    key=f"garcom-vincular-{comanda.comanda_id}",
                                ):
                                    pedido_id = opcoes[selecionado].id
                                    _executar_write(
                                        sessao,
                                        partial(
                                            aplicacao.vincular_pedido,
                                            contexto,
                                            comanda_id=comanda.comanda_id,
                                            pedido_id=pedido_id,
                                            expected_version=comanda.versao,
                                        ),
                                    )

                            if st.button(
                                "Solicitar conta",
                                key=f"garcom-conta-{comanda.comanda_id}",
                            ):
                                _executar_write(
                                    sessao,
                                    partial(
                                        aplicacao.solicitar_conta,
                                        contexto,
                                        comanda_id=comanda.comanda_id,
                                        expected_version=comanda.versao,
                                    ),
                                )

                        elif comanda.status == StatusComanda.CONTA_SOLICITADA.value:
                            if st.button(
                                "Retomar consumo",
                                key=f"garcom-retomar-{comanda.comanda_id}",
                            ):
                                _executar_write(
                                    sessao,
                                    partial(
                                        aplicacao.retomar_consumo,
                                        contexto,
                                        comanda_id=comanda.comanda_id,
                                        expected_version=comanda.versao,
                                    ),
                                )
                            st.info(
                                "Pagamento e fechamento exigem alçada financeira/gerencial."
                            )
                        else:
                            st.info(
                                "Esta etapa da comanda exige caixa/gerência; "
                                "a interface do garçom permanece somente leitura."
                            )

            if not painel.mesas:
                st.info("Nenhuma mesa disponível na sua alçada.")

            if perfil_garcom:
                st.caption(
                    "Alçada do garçom: somente comandas sob sua responsabilidade; "
                    "ações financeiras não são liberadas."
                )
            else:
                st.caption("Alçada gerencial: visão completa do salão no mesmo escopo.")

            _ = mesas_por_id
        except (ErroGarcom, ErroSalao) as exc:
            codigo = getattr(exc, "codigo", type(exc).__name__)
            st.error(f"Operação recusada: {codigo}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Não foi possível atualizar o atendimento: {type(exc).__name__}")
        finally:
            if sessao is not None:
                sessao.close()

    _painel()
