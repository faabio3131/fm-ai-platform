"""UI Streamlit comercial de mesas e comandas V1."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from application.salao_transacoes import AplicacaoSalaoV1
from core.pedidos.modelos_orm import PedidoORM
from core.salao import (
    ErroSalao,
    MetodoFechamento,
    RepositorioSalaoSQLAlchemy,
    ServicoSalao,
    StatusComanda,
    StatusMesa,
)
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

_AUTH_SESSION_KEY = "_fm_ai_authenticated_identity_v1"


def _contexto_comercial() -> ContextoExecucao:
    identidade = st.session_state.get(_AUTH_SESSION_KEY)
    if not isinstance(identidade, IdentidadeUsuario) or not identidade.ativo:
        raise PermissionError("identidade_autenticada_ausente")
    return identidade.contexto(
        origem="salao_streamlit",
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
    )


def _resolver_contexto(
    *, engine: Any, contexto: ContextoExecucao | None
) -> ContextoExecucao:
    if contexto is not None:
        if os.getenv("FM_AI_TEST_MODE") != "1":
            raise RuntimeError("contexto_injetado_so_permitido_em_teste")
        from .runtime_teste import preparar_schema_teste

        preparar_schema_teste(engine)
        return contexto

    identidade = st.session_state.get(_AUTH_SESSION_KEY)
    if isinstance(identidade, IdentidadeUsuario) and identidade.ativo:
        return _contexto_comercial()

    if os.getenv("FM_AI_TEST_MODE") == "1":
        from .runtime_teste import contexto_salao_teste, preparar_schema_teste

        preparar_schema_teste(engine)
        return contexto_salao_teste(
            correlation_id=str(uuid4()),
            solicitado_em=datetime.now(timezone.utc),
            papel="gerente",
        )
    raise PermissionError("identidade_autenticada_ausente")


def _centavos(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"))


def render_salao(
    *,
    engine: Any,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao | None = None,
) -> None:
    """Renderiza o Salão no runtime comercial ou em E2E explicitamente isolado."""

    contexto = _resolver_contexto(engine=engine, contexto=contexto)
    st.header("🪑 Mesas e Comandas")
    st.caption(
        "Operação de salão V1 — Pedido e Pagamento permanecem domínios autoritativos."
    )

    sessao: Session | None = None
    try:
        sessao = session_factory()
        repositorio = RepositorioSalaoSQLAlchemy(sessao)
        servico = ServicoSalao(repositorio, agora=lambda: datetime.now(timezone.utc))
        aplicacao = AplicacaoSalaoV1(session_factory)
        mapa = servico.listar_mapa(contexto)

        if not mapa.mesas:
            st.info("Nenhuma mesa configurada.")
            return

        comandas_por_mesa: dict[str, list] = {}
        for comanda in mapa.comandas:
            if comanda.mesa_id:
                comandas_por_mesa.setdefault(comanda.mesa_id, []).append(comanda)

        st.dataframe(
            [
                {
                    "Mesa": mesa.codigo,
                    "Nome": mesa.nome or "",
                    "Capacidade": mesa.capacidade,
                    "Status": mesa.status.value,
                    "Comandas ativas": len(comandas_por_mesa.get(mesa.mesa_id, [])),
                }
                for mesa in mapa.mesas
            ],
            width="stretch",
            hide_index=True,
        )

        opcoes_mesa = {f"Mesa {mesa.codigo}": mesa for mesa in mapa.mesas if mesa.ativo}
        nome_mesa = st.selectbox("Mesa", tuple(opcoes_mesa), key="salao-mesa")
        mesa = opcoes_mesa[nome_mesa]
        st.subheader(f"Mesa {mesa.codigo}")
        st.write(f"**Status:** {mesa.status.value}")
        st.write(f"**Capacidade:** {mesa.capacidade}")
        st.write(f"**Versão:** {mesa.versao}")

        def concluir(acao: Callable[[], object]) -> None:
            # A sessão desta tela é somente leitura. Fecha o snapshot antes
            # de abrir a transação autoritativa da Application.
            sessao.close()
            acao()
            st.rerun()

        if mesa.status == StatusMesa.LIVRE:
            if st.button("Abrir comanda", key=f"abrir-{mesa.mesa_id}"):
                concluir(
                    lambda: aplicacao.abrir_comanda(
                        contexto,
                        comanda_id=str(uuid4()),
                        numero=f"M{mesa.codigo}-{uuid4().hex[:6]}",
                        mesa_id=mesa.mesa_id,
                        expected_mesa_version=mesa.versao,
                        idempotency_key=f"ui:abrir:{mesa.mesa_id}:{mesa.versao}",
                    )
                )
            return

        ativas = comandas_por_mesa.get(mesa.mesa_id, [])
        if not ativas:
            st.warning("Mesa marcada como ocupada sem comanda ativa; operação bloqueada.")
            return

        opcoes_comanda = {f"{c.numero} · {c.status.value}": c for c in ativas}
        nome_comanda = st.selectbox(
            "Comanda", tuple(opcoes_comanda), key=f"salao-comanda-{mesa.mesa_id}"
        )
        comanda = opcoes_comanda[nome_comanda]
        st.markdown(f"### Comanda {comanda.numero}")
        st.write(f"**Status:** {comanda.status.value}")
        st.write(f"**Total:** R$ {comanda.total:.2f}")
        st.write(f"**Saldo:** R$ {comanda.saldo:.2f}")
        st.write(f"**Versão:** {comanda.versao}")

        participantes = repositorio.listar_participantes(
            contexto.tenant_id, contexto.unidade_id, comanda.comanda_id
        )
        pedidos = repositorio.listar_pedidos(
            contexto.tenant_id, contexto.unidade_id, comanda.comanda_id
        )

        if participantes:
            st.caption(
                "Participantes: "
                + ", ".join(p.apelido or p.participante_id for p in participantes)
            )
        if pedidos:
            st.dataframe(
                [
                    {
                        "Pedido": item.pedido_id,
                        "Participante": item.participante_id or "",
                        "Valor": f"R$ {item.valor:.2f}",
                    }
                    for item in pedidos
                ],
                width="stretch",
                hide_index=True,
            )

        if comanda.status in {StatusComanda.ABERTA, StatusComanda.EM_CONSUMO}:
            if not pedidos and st.button(
                "Cancelar comanda", key=f"cancelar-{comanda.comanda_id}"
            ):
                concluir(
                    lambda: aplicacao.cancelar_comanda(
                        contexto,
                        comanda_id=comanda.comanda_id,
                        expected_version=comanda.versao,
                        idempotency_key=(
                            f"ui:cancelar:{comanda.comanda_id}:{comanda.versao}"
                        ),
                        pedidos_resolvidos=True,
                    )
                )

            with st.expander("Participantes e consumo", expanded=True):
                apelido = st.text_input(
                    "Novo participante",
                    key=f"participante-nome-{comanda.comanda_id}",
                )
                if st.button(
                    "Adicionar participante", key=f"participante-add-{comanda.comanda_id}"
                ):
                    if not apelido.strip():
                        raise ErroSalao("participante_sem_apelido")
                    concluir(
                        lambda: aplicacao.adicionar_participante(
                            contexto,
                            comanda_id=comanda.comanda_id,
                            participante_id=str(uuid4()),
                            apelido=apelido.strip(),
                            expected_version=comanda.versao,
                            idempotency_key=(
                                f"ui:participante:{comanda.comanda_id}:{comanda.versao}"
                            ),
                        )
                    )

                vinculados = {item.pedido_id for item in pedidos}
                consulta_pedidos = (
                    select(PedidoORM)
                    .where(
                        PedidoORM.tenant_id == contexto.tenant_id,
                        PedidoORM.unidade_id == contexto.unidade_id,
                        PedidoORM.status != "cancelado",
                    )
                    .order_by(PedidoORM.criado_em, PedidoORM.id)
                )
                if vinculados:
                    consulta_pedidos = consulta_pedidos.where(
                        PedidoORM.id.notin_(vinculados)
                    )
                pedidos_disponiveis = tuple(sessao.scalars(consulta_pedidos))
                if pedidos_disponiveis:
                    opcoes_pedido = {
                        f"{item.id} · R$ {Decimal(str(item.total)):.2f}": item
                        for item in pedidos_disponiveis
                    }
                    pedido_nome = st.selectbox(
                        "Pedido disponível",
                        tuple(opcoes_pedido),
                        key=f"pedido-add-select-{comanda.comanda_id}",
                    )
                    participante_opcoes: dict[str, str | None] = {"Sem participante": None}
                    participante_opcoes.update(
                        {
                            p.apelido or p.participante_id: p.participante_id
                            for p in participantes
                        }
                    )
                    participante_nome = st.selectbox(
                        "Atribuir a",
                        tuple(participante_opcoes),
                        key=f"pedido-participante-{comanda.comanda_id}",
                    )
                    if st.button(
                        "Adicionar pedido", key=f"pedido-add-{comanda.comanda_id}"
                    ):
                        pedido = opcoes_pedido[pedido_nome]
                        concluir(
                            lambda: aplicacao.vincular_pedido(
                                contexto,
                                comanda_id=comanda.comanda_id,
                                pedido_id=pedido.id,
                                participante_id=participante_opcoes[participante_nome],
                                expected_version=comanda.versao,
                                idempotency_key=(
                                    f"ui:pedido:{comanda.comanda_id}:{pedido.id}"
                                ),
                            )
                        )
                else:
                    st.caption("Nenhum pedido disponível para vincular.")

            livres = [m for m in mapa.mesas if m.ativo and m.status == StatusMesa.LIVRE]
            if livres:
                opcoes_destino = {f"Mesa {m.codigo}": m for m in livres}
                destino_nome = st.selectbox(
                    "Transferir para",
                    tuple(opcoes_destino),
                    key=f"transferir-destino-{comanda.comanda_id}",
                )
                if st.button("Transferir comanda", key=f"transferir-{comanda.comanda_id}"):
                    mesa_destino = opcoes_destino[destino_nome]
                    concluir(
                        lambda: aplicacao.transferir_comanda(
                            contexto,
                            comanda_id=comanda.comanda_id,
                            mesa_destino_id=mesa_destino.mesa_id,
                            expected_comanda_version=comanda.versao,
                            expected_origem_version=mesa.versao,
                            expected_destino_version=mesa_destino.versao,
                            idempotency_key=(
                                f"ui:transferir:{comanda.comanda_id}:{comanda.versao}"
                            ),
                        )
                    )

            if len(pedidos) > 1:
                pedido_separar = st.selectbox(
                    "Pedido para nova comanda",
                    tuple(item.pedido_id for item in pedidos),
                    key=f"separar-pedido-{comanda.comanda_id}",
                )
                if st.button("Separar pedido", key=f"separar-{comanda.comanda_id}"):
                    concluir(
                        lambda: aplicacao.separar_comanda(
                            contexto,
                            origem_id=comanda.comanda_id,
                            nova_comanda_id=str(uuid4()),
                            novo_numero=f"{comanda.numero}-S{uuid4().hex[:3]}",
                            pedido_ids=(pedido_separar,),
                            expected_origem_version=comanda.versao,
                            idempotency_key=(
                                f"ui:separar:{comanda.comanda_id}:{pedido_separar}"
                            ),
                        )
                    )

            outras = [c for c in mapa.comandas if c.comanda_id != comanda.comanda_id]
            if outras:
                opcoes_juntar = {f"{c.numero} · {c.status.value}": c for c in outras}
                juntar_nome = st.selectbox(
                    "Juntar com",
                    tuple(opcoes_juntar),
                    key=f"juntar-destino-{comanda.comanda_id}",
                )
                if st.button("Juntar comandas", key=f"juntar-{comanda.comanda_id}"):
                    comanda_destino = opcoes_juntar[juntar_nome]
                    concluir(
                        lambda: aplicacao.juntar_comandas(
                            contexto,
                            origem_id=comanda.comanda_id,
                            destino_id=comanda_destino.comanda_id,
                            expected_origem_version=comanda.versao,
                            expected_destino_version=comanda_destino.versao,
                            idempotency_key=(
                                f"ui:juntar:{comanda.comanda_id}:{comanda_destino.comanda_id}"
                            ),
                        )
                    )

            if st.button("Solicitar conta", key=f"conta-{comanda.comanda_id}"):
                concluir(
                    lambda: aplicacao.solicitar_conta(
                        contexto,
                        comanda_id=comanda.comanda_id,
                        expected_version=comanda.versao,
                        idempotency_key=f"ui:conta:{comanda.comanda_id}:{comanda.versao}",
                    )
                )

        elif comanda.status == StatusComanda.CONTA_SOLICITADA:
            if st.button("Retomar consumo", key=f"retomar-{comanda.comanda_id}"):
                concluir(
                    lambda: aplicacao.retomar_consumo(
                        contexto,
                        comanda_id=comanda.comanda_id,
                        expected_version=comanda.versao,
                        idempotency_key=(
                            f"ui:retomar:{comanda.comanda_id}:{comanda.versao}"
                        ),
                    )
                )

            st.markdown("#### Divisão da conta")
            metade = (comanda.saldo / Decimal(2)).quantize(Decimal("0.01"))
            pix = st.number_input(
                "Valor PIX",
                min_value=0.01,
                max_value=float(comanda.saldo),
                value=float(metade),
                step=0.01,
                key=f"pix-{comanda.comanda_id}",
            )
            restante = comanda.saldo - _centavos(pix)
            st.write(f"Dinheiro: R$ {restante:.2f}")
            if st.button(
                "Definir pagamento misto", key=f"dividir-{comanda.comanda_id}"
            ):
                divisoes = [(MetodoFechamento.PIX, _centavos(pix), None)]
                if restante > 0:
                    divisoes.append((MetodoFechamento.DINHEIRO, restante, None))
                concluir(
                    lambda: aplicacao.definir_divisao_pagamento(
                        contexto,
                        comanda_id=comanda.comanda_id,
                        expected_version=comanda.versao,
                        idempotency_key=(
                            f"ui:dividir:{comanda.comanda_id}:{comanda.versao}"
                        ),
                        divisoes=tuple(divisoes),
                    )
                )

        elif comanda.status in {
            StatusComanda.FECHAMENTO_EM_ANDAMENTO,
            StatusComanda.PARCIALMENTE_PAGA,
        }:
            parcelas = repositorio.listar_parcelas(
                contexto.tenant_id, contexto.unidade_id, comanda.comanda_id
            )
            total_pago = repositorio.total_pago_confirmado(
                contexto.tenant_id, contexto.unidade_id, comanda.comanda_id
            )
            st.write(f"**Confirmado:** R$ {total_pago:.2f}")
            acumulado = Decimal("0.00")
            proxima = None
            for parcela in parcelas:
                acumulado += parcela.valor
                if acumulado > total_pago:
                    proxima = parcela
                    break
            if proxima is not None:
                st.caption(
                    f"Próxima parcela: {proxima.metodo.value} · R$ {proxima.valor:.2f}"
                )
                if Permissao.PAGAMENTO_CONFIRMAR in contexto.permissoes:
                    pagamento_id = st.text_input(
                        "ID do pagamento canônico já confirmado",
                        key=f"pagamento-canonico-{comanda.comanda_id}-{proxima.ordem}",
                        help=(
                            "O Salão não cria nem simula pagamentos. Informe o ID de um "
                            "Pagamento V1 realmente liquidado para esta comanda."
                        ),
                    )
                    if st.button(
                        "Vincular pagamento confirmado",
                        key=f"confirmar-parcela-{comanda.comanda_id}-{proxima.ordem}",
                    ):
                        if not pagamento_id.strip():
                            raise ErroSalao("pagamento_nao_confirmado")
                        concluir(
                            lambda: aplicacao.registrar_pagamento_confirmado(
                                contexto,
                                pagamento_id=pagamento_id.strip(),
                                comanda_id=comanda.comanda_id,
                                metodo=proxima.metodo,
                                valor=proxima.valor,
                                expected_version=comanda.versao,
                                idempotency_key=(
                                    f"ui:pay:{comanda.comanda_id}:{proxima.ordem}:"
                                    f"{pagamento_id.strip()}"
                                ),
                            )
                        )
                else:
                    st.info(
                        "A confirmação financeira exige Caixa/Gerência com "
                        "PAGAMENTO_CONFIRMAR. O Salão permanece somente leitura nesta etapa."
                    )
            elif comanda.saldo == Decimal("0.00"):
                st.success("Saldo integralmente confirmado.")
                if st.button("Fechar comanda", key=f"fechar-{comanda.comanda_id}"):
                    concluir(
                        lambda: aplicacao.fechar_comanda(
                            contexto,
                            comanda_id=comanda.comanda_id,
                            expected_version=comanda.versao,
                            idempotency_key=(
                                f"ui:fechar:{comanda.comanda_id}:{comanda.versao}"
                            ),
                            pedidos_resolvidos=True,
                        )
                    )
    except ErroSalao as exc:
        st.error(f"Operação de salão recusada: {exc.codigo}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Não foi possível carregar o salão: {type(exc).__name__}")
    finally:
        if sessao is not None:
            sessao.close()
