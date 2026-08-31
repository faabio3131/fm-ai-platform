"""Interface comercial canônica do Agente Inteligente de Atendimento V1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from application.assistente_atendimento_runtime import (
    ResultadoRuntimeAssistente,
    RuntimeAssistenteAtendimentoV1,
)
from application.checkout import CheckoutInvalido
from core.ai_router import ErroAIRouter
from core.assistente_atendimento.atendimento_modelos import (
    EstadoAtendimento,
    ModalidadePedidoAtendimento,
)
from core.assistente_atendimento.erros import ErroAssistenteAtendimento
from core.assistente_atendimento.flags import assistente_atendimento_v1_enabled
from core.crm.erros import ErroCRM
from core.delivery.erros import ErroDelivery
from core.gerente_ia.erros import ErroGerenteIA
from core.integracoes.google_maps import ErroGoogleMaps
from core.integracoes.modelos import ErroConfiguracaoServico
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.autenticacao import IdentidadeUsuario

_RESULTADO_KEY = "_assistente_atendimento_runtime_resultado_v1"
_IDEMPOTENCIA_KEY = "_assistente_atendimento_idempotencia_v1"
_CONVERSA_KEY = "_assistente_atendimento_conversa_v1"
_ERROS_RUNTIME_SEGURO = (
    CheckoutInvalido,
    ErroAIRouter,
    ErroAssistenteAtendimento,
    ErroCRM,
    ErroDelivery,
    ErroGoogleMaps,
    ErroConfiguracaoServico,
    ErroGerenteIA,
    LookupError,
    PermissionError,
    RuntimeError,
    SQLAlchemyError,
    ValueError,
)


def _metodos_pagamento() -> dict[str, MetodoPagamento]:
    return {
        "Pix": MetodoPagamento.PIX,
        "Dinheiro": MetodoPagamento.DINHEIRO,
        "Cartão de crédito": MetodoPagamento.CARTAO_CREDITO,
        "Cartão de débito": MetodoPagamento.CARTAO_DEBITO,
        "Pagamento na entrega": MetodoPagamento.PAGAMENTO_NA_ENTREGA,
    }


def _limpar_jornada() -> None:
    for key in (_RESULTADO_KEY, _IDEMPOTENCIA_KEY, _CONVERSA_KEY):
        st.session_state.pop(key, None)


def render_assistente_atendimento_v1(
    *,
    session_factory: Callable[[], Any],
    identidade: IdentidadeUsuario,
    nome_publico: str,
) -> None:
    """Renderiza somente a composição canônica; nenhum fluxo Mica/Fake é chamado."""

    nome = " ".join(nome_publico.split()) or "Assistente de Atendimento"
    st.header(f"💬 {nome} — Funcionário Digital V1")
    st.caption(
        "A IA interpreta a conversa. Cliente, catálogo, endereço, confirmação, "
        "pedido e pagamento são validados por serviços determinísticos do Kordena."
    )

    if not assistente_atendimento_v1_enabled():
        st.info(
            "O Assistente de Atendimento está em rollout controlado neste ambiente. "
            "Nenhum fluxo legado/fake é executado quando a função está desativada."
        )
        return

    runtime = RuntimeAssistenteAtendimentoV1(session_factory)
    telefone = st.text_input(
        "WhatsApp do cliente",
        value="",
        placeholder="Ex.: 5511999999999",
        key="assistente_v1_cliente",
    )
    modalidade_entrada = st.radio(
        "Entrada do cliente",
        ("Texto", "Áudio"),
        horizontal=True,
        key="assistente_v1_modalidade_entrada",
    )
    mensagem = ""
    audio_upload = None
    if modalidade_entrada == "Texto":
        mensagem = st.text_area(
            "Mensagem do cliente",
            value="",
            placeholder=(
                "Ex.: Quero 2 X-Bacon para entrega na Rua X, 123, "
                "CEP 00000-000."
            ),
            key="assistente_v1_mensagem",
        )
    else:
        audio_upload = st.file_uploader(
            "Áudio do cliente",
            type=("ogg", "oga", "mp3", "wav", "m4a", "webm"),
            accept_multiple_files=False,
            key="assistente_v1_audio",
        )
        if audio_upload is not None:
            st.audio(audio_upload.getvalue())

    c_analisar, c_nova = st.columns(2)
    if c_analisar.button(
        f"Analisar com {nome}",
        type="primary",
        use_container_width=True,
    ):
        entrada_invalida = (
            not telefone.strip()
            or (modalidade_entrada == "Texto" and not mensagem.strip())
            or (modalidade_entrada == "Áudio" and audio_upload is None)
        )
        if entrada_invalida:
            st.error("WhatsApp e conteúdo de atendimento são obrigatórios.")
        else:
            conversa_id = str(st.session_state.get(_CONVERSA_KEY) or uuid4())
            st.session_state[_CONVERSA_KEY] = conversa_id
            mensagem_id = str(uuid4())
            try:
                contexto_solicitante = identidade.contexto(
                    origem="streamlit.assistente_atendimento"
                )
                if modalidade_entrada == "Texto":
                    resultado = runtime.interpretar_texto(
                        contexto_solicitante=contexto_solicitante,
                        conversa_id=conversa_id,
                        mensagem_id=mensagem_id,
                        identificador_cliente=telefone,
                        mensagem=mensagem,
                        nome_publico=nome,
                    )
                else:
                    assert audio_upload is not None
                    mime_type = (
                        audio_upload.type
                        if str(audio_upload.type or "").startswith("audio/")
                        else "audio/ogg"
                    )
                    resultado = runtime.interpretar_audio(
                        contexto_solicitante=contexto_solicitante,
                        conversa_id=conversa_id,
                        mensagem_id=mensagem_id,
                        identificador_cliente=telefone,
                        audio=audio_upload.getvalue(),
                        mime_type=mime_type,
                        nome_publico=nome,
                    )
                st.session_state[_RESULTADO_KEY] = resultado
                st.session_state[_IDEMPOTENCIA_KEY] = str(uuid4())
                st.rerun()
            except _ERROS_RUNTIME_SEGURO:
                st.error(
                    "Não foi possível interpretar o atendimento com segurança. "
                    "A integração permanece fail-closed; revise catálogo, CRM, "
                    "IA e, para entrega, Google Maps/política da unidade."
                )

    if c_nova.button("Nova conversa", use_container_width=True):
        _limpar_jornada()
        st.rerun()

    runtime_resultado = st.session_state.get(_RESULTADO_KEY)
    if not isinstance(runtime_resultado, ResultadoRuntimeAssistente):
        return

    resultado = runtime_resultado.resultado

    if resultado.estado is EstadoAtendimento.HANDOFF_HUMANO:
        st.warning(
            "Atendimento encaminhado para humano. "
            f"Motivo técnico: {resultado.handoff_motivo or 'fluxo não resolvido'}."
        )
        return

    carrinho = resultado.carrinho
    if carrinho is None:
        st.info(resultado.mensagem)
        return

    st.subheader("Conferência do carrinho")
    for item in carrinho.itens:
        st.write(f"{item.quantidade}x {item.nome_produto} — R$ {item.subtotal:.2f}")
    st.write(f"Subtotal: **R$ {carrinho.subtotal:.2f}**")
    if carrinho.entrega is not None:
        st.write(f"Taxa de entrega: **R$ {carrinho.taxa_entrega:.2f}**")
    st.write(f"Total atual: **R$ {carrinho.total:.2f}**")
    st.caption(f"Fingerprint: {carrinho.fingerprint[:16]}…")

    if resultado.estado is EstadoAtendimento.AGUARDANDO_DADOS_CLIENTE:
        st.info(
            "Cliente novo identificado. O carrinho não será confirmado antes "
            "do registro mínimo no CRM canônico."
        )
        if st.button("Registrar cliente mínimo no CRM e continuar", type="primary"):
            try:
                atualizado = runtime.registrar_cliente_minimo(
                    runtime_anterior=runtime_resultado,
                    identificador_cliente=telefone,
                )
                st.session_state[_RESULTADO_KEY] = atualizado
                st.rerun()
            except _ERROS_RUNTIME_SEGURO:
                st.error(
                    "Não foi possível registrar o cliente com segurança. "
                    "Nenhum checkout foi executado."
                )
        return

    if resultado.estado is EstadoAtendimento.AGUARDANDO_MODALIDADE_ENTREGA:
        st.info("O cliente ainda não definiu retirada ou entrega.")
        modalidade_label = st.radio(
            "Modalidade do pedido",
            ("Retirada", "Entrega"),
            horizontal=True,
            key="assistente_v1_modalidade_pedido",
        )
        if st.button("Confirmar modalidade", type="primary"):
            modalidade = (
                ModalidadePedidoAtendimento.RETIRADA
                if modalidade_label == "Retirada"
                else ModalidadePedidoAtendimento.ENTREGA
            )
            try:
                atualizado = runtime.definir_modalidade(
                    runtime_anterior=runtime_resultado,
                    modalidade=modalidade,
                )
                st.session_state[_RESULTADO_KEY] = atualizado
                st.rerun()
            except _ERROS_RUNTIME_SEGURO:
                st.error("A modalidade não pôde ser alterada com segurança.")
        return

    if resultado.estado is EstadoAtendimento.AGUARDANDO_ENDERECO_ENTREGA:
        st.info(
            "Entrega exige endereço validado pelo Google Maps e política de área "
            "da unidade antes da confirmação do pedido."
        )
        endereco = st.text_input(
            "Endereço completo de entrega",
            value=carrinho.endereco_solicitado or "",
            placeholder="Rua, número, bairro, cidade - UF, CEP",
            key="assistente_v1_endereco_entrega",
        )
        cep = st.text_input(
            "CEP",
            value="",
            placeholder="00000-000",
            key="assistente_v1_cep_entrega",
        )
        if st.button("Validar endereço, área, taxa e ETA", type="primary"):
            try:
                atualizado = runtime.cotar_entrega(
                    runtime_anterior=runtime_resultado,
                    endereco_texto=endereco,
                    cep=cep,
                )
                st.session_state[_RESULTADO_KEY] = atualizado
                st.rerun()
            except _ERROS_RUNTIME_SEGURO:
                st.error(
                    "Não foi possível validar esta entrega. Nenhuma taxa, ETA ou "
                    "pedido foi presumido. Confira endereço/CEP e a configuração "
                    "Google Maps/áreas da unidade."
                )
        return

    if carrinho.entrega is not None:
        entrega = carrinho.entrega
        st.subheader("Entrega validada")
        st.write(entrega.endereco_formatado)
        st.write(
            f"Área: **{entrega.nome_area}** · "
            f"Distância: **{entrega.distancia_metros / 1000:.1f} km** · "
            f"ETA de trajeto: **{entrega.eta_rota_minutos} min**"
        )
        st.write(
            f"Prazo operacional: **{entrega.sla_minutos}-{entrega.sla_maxutos} min** · "
            f"Taxa: **R$ {entrega.taxa:.2f}**"
        )

    if resultado.estado is EstadoAtendimento.CHECKOUT_REGISTRADO:
        st.success(resultado.mensagem)
        if resultado.checkout is not None:
            st.write(f"Pedido: {resultado.checkout.pedido_id}")
            if resultado.checkout.pagamento_id is not None:
                status = (
                    resultado.checkout.pagamento_status.value
                    if resultado.checkout.pagamento_status is not None
                    else "pendente"
                )
                st.write(
                    f"Pagamento: {resultado.checkout.pagamento_id} — **{status}**"
                )
        return

    st.warning(
        "Nenhum efeito comercial definitivo ocorreu ainda. "
        "Confirme o carrinho exato abaixo."
    )
    metodo_label = st.selectbox(
        "Forma de pagamento solicitada",
        list(_metodos_pagamento()),
        key="assistente_v1_metodo",
    )
    confirmado = st.checkbox(
        "Confirmo que o cliente revisou e aprovou exatamente este carrinho",
        key="assistente_v1_confirmacao",
    )

    if st.button("Confirmar pedido no checkout canônico", type="primary"):
        try:
            final = runtime.confirmar(
                runtime_anterior=runtime_resultado,
                confirmacao_cliente=confirmado,
                fingerprint_confirmado=carrinho.fingerprint,
                metodo=_metodos_pagamento()[metodo_label],
                idempotency_key=str(
                    st.session_state.get(_IDEMPOTENCIA_KEY) or uuid4()
                ),
            )
            st.session_state[_RESULTADO_KEY] = ResultadoRuntimeAssistente(
                contexto=runtime_resultado.contexto,
                resultado=final,
            )
            st.rerun()
        except _ERROS_RUNTIME_SEGURO:
            st.error(
                "O checkout foi recusado ou falhou de forma segura. "
                "Não assuma pagamento, estoque ou produção confirmados."
            )
