"""Superfície comercial autenticada do Delivery Próprio V1."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import streamlit as st
from sqlalchemy.orm import Session

from application.delivery_operacao_comercial import (
    ErroDeliveryComercial,
    acompanhar_delivery_comercial,
    abrir_carrinho_delivery_comercial,
    adicionar_item_delivery_comercial,
    cancelar_delivery_comercial,
    confirmar_delivery_comercial,
    cotar_endereco_delivery_comercial,
    listar_clientes_delivery_comercial,
    obter_carrinho_delivery_comercial,
    repetir_delivery_comercial,
    resolver_contexto_jornada_delivery,
)
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Permissao

from .erros import ErroDelivery
from .flags import delivery_v1_access_allowed, delivery_v1_enabled
from .modelos import StatusCarrinhoDelivery

SessionFactory = Callable[[], Session]


def _executar(acao):
    try:
        return acao()
    except ErroDelivery as exc:
        st.error(f"Não foi possível concluir: {exc.codigo}")
    except (ErroDeliveryComercial, PermissionError, LookupError, ValueError) as exc:
        st.error(f"Não foi possível concluir: {exc}")
    return None


def _limpar_jornada() -> None:
    st.session_state.pop("_delivery_comercial_carrinho_id", None)
    st.session_state.pop("_delivery_comercial_pedido_id", None)


def render_delivery_v1(
    *,
    session_factory: SessionFactory,
    identidade: IdentidadeUsuario,
) -> None:
    """Renderiza Delivery usando somente identidade e authorities comerciais reais."""

    if not delivery_v1_enabled():
        st.info("Delivery Próprio V1 está desabilitado neste ambiente.")
        return
    if not delivery_v1_access_allowed(identidade.permissoes):
        st.error("Seu perfil não possui alçada para operar o Delivery Próprio.")
        return

    st.header("🛵 Delivery Próprio")
    st.caption(
        "Jornada comercial vinculada ao cliente, catálogo, Checkout, Estoque e Entrega canônicos."
    )
    st.caption(
        f"Escopo ativo: {identidade.tenant_id} / {identidade.unidade_id} — "
        "definido pela identidade autenticada."
    )

    clientes = _executar(
        lambda: listar_clientes_delivery_comercial(
            identidade=identidade,
            session_factory=session_factory,
        )
    )
    if not clientes:
        st.warning("Nenhum cliente CRM disponível no escopo ativo para iniciar um delivery.")
        return

    cliente_ids = [cliente.cliente_id for cliente in clientes]
    cliente_anterior = st.session_state.get("_delivery_comercial_cliente_id")
    indice = cliente_ids.index(cliente_anterior) if cliente_anterior in cliente_ids else 0
    cliente_id = st.selectbox(
        "Cliente CRM",
        cliente_ids,
        index=indice,
        key="_delivery_comercial_cliente_select",
    )
    if cliente_id != cliente_anterior:
        st.session_state["_delivery_comercial_cliente_id"] = cliente_id
        _limpar_jornada()

    contexto = _executar(
        lambda: resolver_contexto_jornada_delivery(
            identidade=identidade,
            cliente_id=cliente_id,
            session_factory=session_factory,
        )
    )
    if contexto is None:
        return

    st.info(
        "📍 Endereço validado: "
        f"{contexto.endereco.endereco_formatado} · CEP {contexto.endereco.cep}"
    )

    carrinho_id = st.session_state.get("_delivery_comercial_carrinho_id")
    carrinho = None
    if isinstance(carrinho_id, str):
        carrinho = _executar(
            lambda: obter_carrinho_delivery_comercial(
                identidade=identidade,
                cliente_id=cliente_id,
                carrinho_id=carrinho_id,
                session_factory=session_factory,
            )
        )

    if carrinho is None:
        if st.button("🛒 Iniciar novo pedido", type="primary"):
            novo_id = f"cart-{uuid4().hex[:20]}"
            novo = _executar(
                lambda: abrir_carrinho_delivery_comercial(
                    identidade=identidade,
                    cliente_id=cliente_id,
                    carrinho_id=novo_id,
                    session_factory=session_factory,
                )
            )
            if novo is not None:
                st.session_state["_delivery_comercial_carrinho_id"] = novo.carrinho_id
                st.rerun()
    else:
        if carrinho.status is StatusCarrinhoDelivery.ABERTO:
            st.subheader("1. Cardápio")
            if not contexto.catalogo:
                st.warning("Nenhum produto com ficha/estoque disponível para esta unidade.")
            else:
                for produto in contexto.catalogo:
                    col_nome, col_qtd, col_acao = st.columns([5, 2, 2])
                    with col_nome:
                        st.markdown(f"**{produto.nome}**")
                        st.caption(
                            f"R$ {produto.preco:.2f} · capacidade atual {produto.estoque_disponivel}"
                        )
                    with col_qtd:
                        quantidade = st.number_input(
                            "Qtd.",
                            min_value=1,
                            max_value=100,
                            value=1,
                            key=f"delivery_qtd_{produto.produto_id}",
                        )
                    with col_acao:
                        if st.button(
                            "Adicionar",
                            key=f"delivery_add_{produto.produto_id}",
                            use_container_width=True,
                        ):
                            novo = _executar(
                                lambda p=produto, q=int(quantidade): adicionar_item_delivery_comercial(
                                    identidade=identidade,
                                    cliente_id=cliente_id,
                                    carrinho_id=carrinho.carrinho_id,
                                    produto_id=p.produto_id,
                                    quantidade=q,
                                    expected_version=carrinho.versao,
                                    session_factory=session_factory,
                                )
                            )
                            if novo is not None:
                                st.success(f"{produto.nome} adicionado ao carrinho.")
                                st.rerun()

            carrinho = obter_carrinho_delivery_comercial(
                identidade=identidade,
                cliente_id=cliente_id,
                carrinho_id=carrinho.carrinho_id,
                session_factory=session_factory,
            )
            if carrinho is None:
                st.error("Carrinho indisponível no escopo ativo.")
                return

            st.subheader("2. Carrinho e entrega")
            if not carrinho.itens:
                st.info("O carrinho ainda está vazio.")
            else:
                for item in carrinho.itens:
                    st.write(f"• {item.quantidade}x {item.nome} — R$ {item.subtotal:.2f}")
                st.metric("Subtotal", f"R$ {carrinho.subtotal:.2f}")

            if carrinho.endereco is None:
                if st.button("📍 Calcular taxa e SLA no endereço validado"):
                    cotado = _executar(
                        lambda: cotar_endereco_delivery_comercial(
                            identidade=identidade,
                            cliente_id=cliente_id,
                            carrinho_id=carrinho.carrinho_id,
                            expected_version=carrinho.versao,
                            session_factory=session_factory,
                        )
                    )
                    if cotado is not None:
                        st.rerun()
            elif carrinho.cotacao is not None:
                st.success(
                    f"{carrinho.cotacao.nome_area}: taxa R$ {carrinho.taxa_entrega:.2f} · "
                    f"SLA {carrinho.cotacao.sla_minutos}-{carrinho.cotacao.sla_maxutos} min"
                )

            st.subheader("3. Benefícios e fechamento")
            st.caption(
                "Cupom e cashback não são fabricados pela UI. Quando houver reserva válida, "
                "o Checkout canônico avalia e aplica os valores já resolvidos pela política."
            )
            st.write(f"Cupom reservado: R$ {carrinho.desconto_cupom:.2f}")
            st.write(f"Cashback reservado: R$ {carrinho.cashback_reservado:.2f}")
            st.metric("Total estimado", f"R$ {carrinho.total:.2f}")

            metodos = {
                "Pix": MetodoPagamento.PIX,
                "Cartão de crédito": MetodoPagamento.CARTAO_CREDITO,
                "Cartão de débito": MetodoPagamento.CARTAO_DEBITO,
                "Pagamento na entrega": MetodoPagamento.PAGAMENTO_NA_ENTREGA,
            }
            metodo_label = st.selectbox("Forma de pagamento", list(metodos))
            pode_confirmar = {
                Permissao.PEDIDO_ALTERAR,
                Permissao.PAGAMENTO_REGISTRAR,
            }.issubset(identidade.permissoes)
            if not pode_confirmar:
                st.warning(
                    "Seu perfil pode montar e consultar o pedido, mas não possui alçada para finalizar o checkout."
                )
            if st.button(
                "✅ Confirmar pedido",
                type="primary",
                use_container_width=True,
                disabled=(
                    not pode_confirmar
                    or not carrinho.itens
                    or carrinho.cotacao is None
                ),
            ):
                chave = f"delivery-ui:{carrinho.carrinho_id}"
                resultado = _executar(
                    lambda: confirmar_delivery_comercial(
                        identidade=identidade,
                        cliente_id=cliente_id,
                        carrinho_id=carrinho.carrinho_id,
                        metodo_pagamento=metodos[metodo_label],
                        idempotency_key=chave,
                        session_factory=session_factory,
                    )
                )
                if resultado is not None:
                    st.session_state["_delivery_comercial_pedido_id"] = resultado.pedido_id
                    st.success("Pedido criado no Checkout canônico e vinculado à Entrega V1.")
                    st.rerun()
        else:
            st.success("Carrinho já confirmado no fluxo comercial.")
            if carrinho.pedido_id:
                st.session_state["_delivery_comercial_pedido_id"] = carrinho.pedido_id

    pedido_id = st.session_state.get("_delivery_comercial_pedido_id")
    if not isinstance(pedido_id, str):
        return

    st.markdown("---")
    st.subheader("4. Acompanhamento")
    tracking = _executar(
        lambda: acompanhar_delivery_comercial(
            identidade=identidade,
            cliente_id=cliente_id,
            pedido_id=pedido_id,
            session_factory=session_factory,
        )
    )
    if tracking is None:
        return
    st.write(f"Pedido: `{tracking.pedido_id}`")
    st.write(f"Pedido: **{tracking.status_pedido.value}**")
    st.write(f"Entrega: **{tracking.status_entrega.value}**")
    st.metric("Total canônico", f"R$ {tracking.total:.2f}")
    if tracking.eventos:
        with st.expander("Histórico logístico"):
            for evento in tracking.eventos:
                st.write(f"• {evento.ocorrido_em:%d/%m/%Y %H:%M} — {evento.tipo}")

    col_cancelar, col_repetir = st.columns(2)
    with col_cancelar:
        if Permissao.PEDIDO_CANCELAR in identidade.permissoes:
            with st.expander("Cancelar pedido"):
                motivo = st.text_input(
                    "Motivo",
                    value="Solicitação do cliente",
                    key="delivery_cancel_motivo",
                )
                if st.button("Cancelar no fluxo canônico", type="secondary"):
                    cancelado = _executar(
                        lambda: cancelar_delivery_comercial(
                            identidade=identidade,
                            cliente_id=cliente_id,
                            pedido_id=pedido_id,
                            motivo=motivo,
                            idempotency_key=f"delivery-ui-cancel:{pedido_id}",
                            session_factory=session_factory,
                        )
                    )
                    if cancelado is not None:
                        st.success("Pedido, reserva, obrigação pendente e entrega reconciliados.")
                        st.rerun()
        else:
            st.caption("Cancelamento exige alçada de pedido.cancelar.")

    with col_repetir:
        if st.button("🔁 Repetir com preços/estoque atuais", use_container_width=True):
            novo_id = f"cart-repeat-{uuid4().hex[:16]}"
            repetido = _executar(
                lambda: repetir_delivery_comercial(
                    identidade=identidade,
                    cliente_id=cliente_id,
                    pedido_id=pedido_id,
                    novo_carrinho_id=novo_id,
                    session_factory=session_factory,
                )
            )
            if repetido is not None:
                st.session_state["_delivery_comercial_carrinho_id"] = repetido.carrinho_id
                st.session_state.pop("_delivery_comercial_pedido_id", None)
                st.success("Novo carrinho reconstruído com o estado comercial atual.")
                st.rerun()
